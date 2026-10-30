from pathlib import Path
import re

try:
    from .svg_kit.primitives import legacy_defs
except ImportError:
    from svg_kit.primitives import legacy_defs


_DEFS_RE = re.compile(br"<defs\b[^>]*>.*?</defs>", re.DOTALL)
_STYLE_RE = re.compile(r"<style>(.*?)</style>", re.DOTALL)


def sync_asset(path: Path, profile: str) -> None:
    original = path.read_bytes()
    matches = list(_DEFS_RE.finditer(original))
    if len(matches) != 1:
        raise ValueError(f"{path.name}: 应恰好有一个 defs，实际为 {len(matches)}")
    match = matches[0]

    style = None
    if profile == "amat":
        style_match = _STYLE_RE.search(match.group().decode("utf-8"))
        if style_match is None:
            raise ValueError(f"{path.name}: 未找到原有 style")
        style = style_match.group(1)

    rendered = legacy_defs(profile, style=style).encode("utf-8")
    updated = original[:match.start()] + rendered + original[match.end():]
    path.write_bytes(updated)
    print(f"[OK] {path.name}: 仅同步 defs（{len(rendered)} bytes）")


def main() -> None:
    user_dir = Path(__file__).resolve().parent / "user"
    sync_asset(user_dir / "amat_metsput.svg", "amat")
    sync_asset(user_dir / "podopener-2200.svg", "podopener")


if __name__ == "__main__":
    main()
