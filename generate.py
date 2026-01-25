import os
import shutil
import tempfile
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path
from subprocess import Popen, PIPE

import jinja2
import markdown
import requests
from bs4 import BeautifulSoup
from pygments.formatters import HtmlFormatter

from config import Config
from data import FolderEntry, FileEntry


@dataclass
class Context:
    tree: FolderEntry

    def _path(self, file: FileEntry) -> list[FolderEntry]:
        chunks = str(file.path).removeprefix(str(self.tree.path)).removeprefix('/').split('/')[:-1]
        iterated = []
        latest = self.tree
        for c in chunks:
            f = next(f for f in latest.folders if f.path.name == c)
            iterated.append(f)
            latest = f
        return iterated

    def route(self, item: FileEntry) -> str:
        chunks = [f.route for f in self._path(item)] + [item.route]
        return '/' + '/'.join(chunks)

    def crumbs(self, item: FileEntry) -> list[str]:
        chunks = [f.title for f in self._path(item)] + [item.title]
        return chunks

class JsGenerationException(Exception):
    def __init__(self, stage: str, message: str):
        super().__init__(stage + ":\n" + message)
        self.stage = stage
        self.message = message

class Generator:
    def __init__(self, config: Config):
        self.config = config
        self.page_template = jinja2.Template((config.template_dir / 'html_template.jinja').read_text())
        self.kotlin_import_template = jinja2.Template((config.template_dir / 'kotlin_import_template.jinja').read_text())
        self.kotlin_template = jinja2.Template((config.template_dir / 'kotlin_template.jinja').read_text())
        self.valid_snippets: dict[str, str] = {}

    def run(self):
        print("[Main] Clearing folders")
        shutil.rmtree(self.config.output_dir, ignore_errors=True)
        self.config.cache_dir.mkdir(parents=True, exist_ok=True)

        print("[Main] Downloading required KLIBs")
        self.prepare_klibs()

        print("[Main] Synchronizing NPM dependencies")
        self.prepare_npm()

        print("[Main] Parsing file tree")
        file_tree = FolderEntry.parse(self.config.source_dir)
        ctx = Context(file_tree)

        print("[Main] Generating files recursively")
        self.generate_files(ctx, file_tree, self.config.output_dir)

        if self.valid_snippets:
            print("[Main] Building Master Bundle")
            self.build_master_bundle()

        print("[Main] Copying extra files")
        for (src, dest) in self.config.extra_files.items():
            dest_path = self.config.output_dir / dest
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.config.template_dir / src, dest_path)

    def build_master_bundle(self):
        print("[Master Bundle] Compiling with kotlinc-js")
        master_kt = "import kotlin.js.JsExport\n" + "\n".join("@JsExport\n" + self.kotlin_template.render(content=source, id=module) for (module, source) in self.valid_snippets.items())
        full_kt = self.kotlin_import_template.render(content=master_kt)
        js_content = self.kotlinc(full_kt, "bundle")

        print("[Master Bundle] Writing to file")
        out_file = self.config.output_dir / 'js' / 'bundle.js'
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(js_content)

    def generate_files(self, ctx: Context, folder: FolderEntry, output_dir: Path):
        for a in folder.assets:
            shutil.copyfile(a, output_dir / a.name)
        for f in folder.files:
            if f.draft: continue
            self.generate_file(ctx, f, output_dir / f.route)
        for f in folder.folders:
            if f.empty: continue
            self.generate_files(ctx, f, output_dir / f.route)

    def generate_file(self, ctx: Context, file: FileEntry, output_file: Path):
        output_file.parent.mkdir(parents=True, exist_ok=True)

        print(f"[Markdown - {ctx.route(file)}] Parsing nested HTML")
        content = file.path.read_text()
        soup = BeautifulSoup(content, 'html.parser')

        for script in soup.find_all('script', {"type": "text/kotlin"}):
            new_html = self.generate_kotlin_snippet(script.text)
            content = content.replace(str(script), new_html, 1)

        print(f"[Markdown - {ctx.route(file)}] Converting Markdown")
        try:
            html_post = self.render_markdown(content)
            print(f"[Markdown - {ctx.route(file)}] Post-processing generated HTML")
            html_processed, summary = self.postprocess_html(html_post)
        except Exception as e:
            traceback.print_exception(e)
            output_file.write_text(self.page_template.render(
                ctx=ctx,
                file=file,
                content=file.path.read_text(),
                page_summary=f"<pre><code>An error occurred rendering this page:\n{traceback.format_exception(e)}</code></pre>",
                syntax_css=self.pygments_css_style()
            ))
            return

        print(f"[Markdown - {ctx.route(file)}] Writing to file")
        output_file.write_text(self.page_template.render(
            ctx=ctx,
            file=file,
            content=html_processed,
            page_summary=summary,
            syntax_css=self.pygments_css_style()
        ))

    def pygments_css_style(self) -> str:
        style_light = HtmlFormatter(style=self.config.render_settings.pygments_style).get_style_defs('.highlight')
        style_dark = HtmlFormatter(style=self.config.render_settings.pygments_style_dark).get_style_defs('.dark-mode .highlight')
        style_dark = style_dark\
            .replace("td.linenos", ".dark-mode td.linenos") \
            .replace("span.linenos", ".dark-mode span.linenos")
        return style_light + "\n" + style_dark

    def generate_kotlin_snippet(self, source: str) -> str:
        snippet_id = uuid.uuid4().hex

        try:
            print(f"[Kotlin - {snippet_id}] Validating snippet")
            self.validate_snippet(source, snippet_id)
            self.valid_snippets[snippet_id] = source
            return f"""
<div id="container-{snippet_id}" class="kt-container card text-left">
 <canvas id="canvas-{snippet_id}" class="d-none kt-canvas"></canvas>
 <div id="plot-{snippet_id}" class="d-none kt-plot">
  <div id="plot-{snippet_id}-light" class="light-only"></div>
  <div id="plot-{snippet_id}-dark" class="dark-only"></div>
 </div>
 <button class="btn btn-action kt-rerun" onclick="bundle.init_{snippet_id}()" aria-label="Re-run snippet">
  <i class="fa fa-refresh" aria-hidden="true"></i>
 </button>
 <script type="text/javascript">bundle.init_{snippet_id}()</script>
 <details id="source-{snippet_id}" class="collapse-panel kt-source">
  <summary class="collapse-header">View Kotlin Source</summary>
  <div class="collapse-content">
```kotlin
{source.strip()}
```
  </div>
 </details>
</div>
            """
        except JsGenerationException as e:
            traceback.print_exception(e)
            return f"```kotlin\n{e.message}\n```"

    def validate_snippet(self, source: str, snippet_id: str):
        full_source = self.kotlin_template.render(content=source, id=snippet_id)
        full_source = self.kotlin_import_template.render(content=full_source)
        self.kotlinc(full_source, snippet_id, check_only = True)

    def render_markdown(self, source: str) -> str:
        extensions = [
            'fenced_code',
            'codehilite',
            'tables',
            'attr_list',
            'md_in_html',
            'mdx_math',
            'meta',
        ]
        extension_configs = {
            'codehilite': {
                'css_class': 'highlight',
                'use_pygments': True,
                'pygments_style': self.config.render_settings.pygments_style,
                'linenums': self.config.render_settings.line_numbers,
            },
            'mdx_math': {
                'enable_dollar_delimiter': True,
            }
        }
        return markdown.markdown(
            source,
            extensions=extensions,
            extension_configs=extension_configs
        )

    def kotlinc(self, source: str, module: str, check_only: bool = False) -> str:
        with tempfile.TemporaryDirectory() as d:
            work_path = Path(d)
            kt_file = work_path / "source.kt"
            kt_file.write_text(source)

            print(f"[Kotlin - {module}] Lowering to IR")
            process = Popen(
                [
                    'kotlinc-js',
                    '-libraries', ':'.join(str((self.config.cache_dir / k).absolute()) for (k, _) in self.config.kotlin_settings.klibs),
                    '-ir-output-dir', str(work_path / 'out' / 'klib'),
                    '-ir-output-name', module,
                    '-Xir-produce-klib-file',
                    *self.config.kotlin_settings.kotlinc_args,
                    str(kt_file)
                ],
                stdout=PIPE,
                stderr=PIPE,
            )
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                raise JsGenerationException("kotlinc threw an exception lowering to IR", stderr.decode())

            if check_only:
                return "/* Source not needed, check passed */"

            print(f"[Kotlin - {module}] Lowering to JS")
            process = Popen(
                [
                    'kotlinc-js',
                    '-libraries', ':'.join(str((self.config.cache_dir / k).absolute()) for (k, _) in self.config.kotlin_settings.klibs),
                    '-ir-output-dir', str(work_path / 'out' / 'js'),
                    '-ir-output-name', module,
                    '-Xir-produce-js',
                    '-Xir-module-kind=commonjs',
                    *self.config.kotlin_settings.kotlinc_args,
                    '-Xinclude=' + str(work_path / 'out' / 'klib' / f'{module}.klib')
                ],
                stdout=PIPE,
                stderr=PIPE,
            )
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                raise Exception("kotlinc threw an exception lowering to JS", stderr.decode())

            bundled_js_path = work_path / "final.js"
            node_path = self.config.cache_dir / "node_modules"

            env = os.environ.copy()
            env["NODE_PATH"] = str(node_path.absolute())

            print(f"[Kotlin - {module}] Generating Bundle")
            bundle_process = Popen(
                [
                    'npx', 'esbuild',
                    str(work_path / 'out' / 'js' / f'{module}.js'),
                    '--bundle',
                    '--minify',
                    '--format=iife',
                    '--global-name=bundle',
                    f'--outfile={bundled_js_path}',
                    f'--resolve-extensions=.js',
                ],
                cwd=str(self.config.cache_dir),
                env=env,
                stdout=PIPE, stderr=PIPE
            )
            stdout, stderr = bundle_process.communicate()
            if bundle_process.returncode != 0:
                raise Exception("Bundling failed", stderr.decode())

            return bundled_js_path.read_text()

    def postprocess_html(self, html: str) -> tuple[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all("img"):
            tag["class"] = list(tag.get("class", [])) + ["img-fluid"]
        for tag in soup.find_all("a"):
            tag["class"] = list(tag.get("class", [])) + ["hyperlink"]
        for tag in soup.find_all("table"):
            if "highlighttable" in tag.get("class", []):
                code = tag.find("td", {"class": "code"})
                code["class"] = []
            else:
                tag["class"] = list(tag.get("class", [])) + ["table", "table-striped", "table-hover"]
        headers = []
        for h in ("h1", "h2", "h3", "h4", "h5", "h6"):
            for tag in soup.find_all(h):
                tag["class"] = list(tag.get("class", [])) + ["content-title"]
                tag_id = tag.text.replace(' ', '-')
                headers.append(f'<a href="#{tag_id}">{tag.text}</a>')
                tag["id"] = tag_id
                tag.append(BeautifulSoup(f' <a href="#{tag_id}" class="ml-5 text-decoration-none">#</a>', "html.parser"))

        if headers:
            return str(soup), "\n".join(headers)
        else:
            return str(soup), ""

    def prepare_klibs(self):
        for (lib, url) in self.config.kotlin_settings.klibs:
            file = self.config.cache_dir / lib
            if not file.exists():
                print(f"[KLIB] Downloading {lib}")
                file.parent.mkdir(parents=True, exist_ok=True)
                res = requests.get(url)
                res.raise_for_status()
                file.write_bytes(res.content)

    def prepare_npm(self):
        shutil.copyfile(self.config.template_dir / "package.json", self.config.cache_dir / "package.json")

        print(f"[NPM] Installing packages in {self.config.cache_dir}")
        process = Popen(
            ['npm', 'install', '--no-save'],
            cwd=str(self.config.cache_dir),
            stdout=PIPE,
            stderr=PIPE,
            text=True
        )
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            raise Exception(f"NPM Install failed:\n{stderr}")
