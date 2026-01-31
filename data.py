import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from frontmatter import Frontmatter

TITLE_PREFIX_RE = re.compile(r"^\d+_")

@dataclass
class FileEntry:
    path: Path
    attrs: dict

    @classmethod
    def parse(cls, path: Path) -> 'FileEntry':
        conf = Frontmatter.read_file(path)
        return cls(path, conf['attributes'] or {})

    @property
    def route(self) -> str:
        return TITLE_PREFIX_RE.sub("", self.path.stem) + ".html"

    @property
    def title(self) -> str:
        if title := self.attrs.get("title"):
            return title
        name = TITLE_PREFIX_RE.sub("", self.path.stem)
        return name.replace("_", " ")

    @property
    def draft(self) -> bool:
        if self.attrs.get("draft", False):
            return True
        if date := self.attrs.get("date", None):
            if datetime.strptime(date, "dd-mm-yyyy") < datetime.now():
                return True
        return False

@dataclass
class FolderEntry:
    path: Path
    folders: list['FolderEntry']
    files: list[FileEntry]
    assets: list[Path]

    @classmethod
    def parse(cls, path: Path) -> 'FolderEntry':
        folders: list[FolderEntry] = []
        files: list[FileEntry] = []
        assets: list[Path] = []
        for e in path.iterdir():
            if e.name.startswith("."):
                continue
            if e.is_dir():
                folders.append(FolderEntry.parse(e))
            elif e.suffix == ".md":
                files.append(FileEntry.parse(e))
            else:
                assets.append(e)

        folders.sort(key=lambda f: f.path.stem)
        files.sort(key=lambda f: f.path.stem)

        routes = set()
        for folder in folders:
            if folder.route in routes:
                raise Exception(f"Duplicate route: {folder.route} in {path}")
            routes.add(folder.route)
        for file in files:
            if file.route in routes:
                raise Exception(f"Duplicate route: {file.route} in {path}")
            routes.add(file.route)

        return cls(path, folders, files, assets)

    @property
    def route(self) -> str:
        return TITLE_PREFIX_RE.sub("", self.path.name)

    @property
    def title(self) -> str:
        name = self.path.stem
        name = TITLE_PREFIX_RE.sub("", name)
        return name.replace("_", " ")

    @property
    def no_content(self):
        return all(f.empty for f in self.folders) and all(f.draft for f in self.files)

    @property
    def empty(self) -> bool:
        return self.no_content and len(self.assets) == 0
