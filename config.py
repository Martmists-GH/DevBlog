from dataclasses import dataclass, asdict
from pathlib import Path

file_root = Path(__file__).parent

@dataclass
class RenderConfig:
    pygments_style: str
    pygments_style_dark: str
    line_numbers: bool

@dataclass
class KotlinConfig:
    klibs: list[tuple[str, str]]
    kotlinc_args: list[str]

@dataclass
class Config:
    source_dir: Path
    output_dir: Path
    template_dir: Path
    cache_dir: Path
    extra_files: dict[str, str]
    render_settings: RenderConfig
    kotlin_settings: KotlinConfig

    @classmethod
    def from_dict(cls, conf: dict) -> 'Config':
        return Config(
            source_dir=Path(conf['source_dir']),
            output_dir=Path(conf['output_dir']),
            template_dir=Path(conf['template_dir']),
            cache_dir=Path(conf['cache_dir']),
            extra_files=conf['extra_files'],
            render_settings=RenderConfig(**conf['render_settings']),
            kotlin_settings=KotlinConfig(**conf['kotlin_settings']),
        )

    def to_dict(self) -> dict:
        return {
            'source_dir': str(self.source_dir),
            'output_dir': str(self.output_dir),
            'template_dir': str(self.template_dir),
            'cache_dir': str(self.cache_dir),
            'extra_files': self.extra_files,
            'render_settings': asdict(self.render_settings),
            'kotlin_settings': asdict(self.kotlin_settings),
        }

    @staticmethod
    def default() -> 'Config':
        return Config(
            source_dir=file_root / "source",
            output_dir=file_root / "public",
            template_dir=file_root / "config",
            cache_dir=file_root / "cache",
            extra_files={'style.css': 'css/style.css'},
            render_settings=RenderConfig(
                pygments_style='default',
                pygments_style_dark='github-dark',
                line_numbers=True
            ),
            kotlin_settings=KotlinConfig(
                klibs=[
                    ("kotlin-stdlib.klib",
                     "https://repo1.maven.org/maven2/org/jetbrains/kotlin/kotlin-stdlib-js/2.3.0/kotlin-stdlib-js-2.3.0.klib"),
                    ("kotlinx-browser.klib",
                     "https://repo1.maven.org/maven2/org/jetbrains/kotlin-wrappers/kotlin-browser-js/2026.1.11/kotlin-browser-js-2026.1.11.klib"),
                    ("kotlinx-dom-api-compat.klib",
                     "https://repo1.maven.org/maven2/org/jetbrains/kotlin/kotlin-dom-api-compat/2.3.0/kotlin-dom-api-compat-2.3.0.klib"),
                    ("lets-plot-kotlin.klib",
                     "https://repo1.maven.org/maven2/org/jetbrains/lets-plot/lets-plot-kotlin-js/4.10.0/lets-plot-kotlin-js-4.10.0.klib"),

                    # Dependencies of lets-plot-kotlin
                    ("lets-plot-commons.klib",
                     "https://repo1.maven.org/maven2/org/jetbrains/lets-plot/commons-js/4.8.2/commons-js-4.8.2.klib"),
                    ("lets-plot-datamodel.klib",
                     "https://repo1.maven.org/maven2/org/jetbrains/lets-plot/datamodel-js/4.8.2/datamodel-js-4.8.2.klib"),
                    ("lets-plot-plot-base.klib",
                     "https://repo1.maven.org/maven2/org/jetbrains/lets-plot/plot-base-js/4.8.2/plot-base-js-4.8.2.klib"),
                    ("lets-plot-plot-builder.klib",
                     "https://repo1.maven.org/maven2/org/jetbrains/lets-plot/plot-builder-js/4.8.2/plot-builder-js-4.8.2.klib"),
                    ("lets-plot-plot-stem.klib",
                     "https://repo1.maven.org/maven2/org/jetbrains/lets-plot/plot-stem-js/4.8.2/plot-stem-js-4.8.2.klib"),
                ],
                kotlinc_args=[
                    '-Xir-dce',
                    '-Xir-minimized-member-names',
                    '-Xoptimize-generated-js',
                ]
            )
        )

