import asyncio
import warnings
from dataclasses import dataclass
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning


@dataclass
class LibInfo:
    package: str
    artifact: str
    version: str
    ext: str = "klib"

    @classmethod
    def parse(cls, lib: str) -> LibInfo:
        parts = lib.split(':')
        if len(parts) in (3, 4):
            return cls(*parts)
        raise Exception(f"Unknown lib info: {lib}")

    @property
    def filename(self):
        return f"{self.artifact}.{self.ext}"

    @property
    def url(self):
        return f"https://repo1.maven.org/maven2/{self.package.replace('.', '/')}/{self.artifact}/{self.version}/{self.artifact}-{self.version}.{self.ext}"

    @property
    def pom_url(self):
        return f"https://repo1.maven.org/maven2/{self.package.replace('.', '/')}/{self.artifact}/{self.version}/{self.artifact}-{self.version}.pom"

loop = asyncio.new_event_loop()
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

class DependencyDownloader:
    def __init__(self, cache_dir: Path, libs: list[str]):
        self.cache_dir = cache_dir
        self.collected: set[str] = set()
        self.libs = libs

    def run(self):
        loop.run_until_complete(self.download_all(self.libs))

    async def download_all(self, libs: list[str]):
        to_dl: list[LibInfo] = []
        for lib in libs:
            info = LibInfo.parse(lib)
            if f"{info.package}:{info.artifact}" not in self.collected:
                to_dl.append(info)
                self.collected.add(f"{info.package}:{info.artifact}")
        tasks = []
        for info in to_dl:
            tasks.append(loop.create_task(self.download(info)))

        await asyncio.gather(*tasks)

    @staticmethod
    def collect_deps(xml: str) -> list[str]:
        soup = BeautifulSoup(xml, 'lxml')
        found = []
        for dep in soup.find_all("dependency"):
            group = dep.find('groupid')
            artifact = dep.find('artifactid')
            version = dep.find('version')
            if not artifact.text.endswith("-js"):
                continue
            if group and artifact and version:
                found.append(f"{group.text}:{artifact.text}:{version.text}")
        return found

    async def download(self, lib: LibInfo):
        out_file = self.cache_dir / lib.filename
        async with aiohttp.ClientSession() as session:
            if not out_file.exists():
                print(f"Downloading {lib.filename}")
                async with session.get(lib.url) as resp:
                    resp.raise_for_status()
                    data = await resp.read()

                with open(out_file, "wb") as f:
                    f.write(data)

            print(f"Searching dependencies for {lib.filename}")
            async with session.get(lib.pom_url) as resp:
                resp.raise_for_status()
                xml = await resp.text()

        libs = await loop.run_in_executor(None, self.collect_deps, xml)
        print(f"Found {len(libs)} dependencies for {lib.filename}")
        await self.download_all(libs)
