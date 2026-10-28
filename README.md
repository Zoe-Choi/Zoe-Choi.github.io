# Zoe-Choi.github.io

Jekyll 기반 GitHub Pages 블로그입니다.

## Local

```powershell
& 'D:\Ruby32-x64\bin\bundle.bat' install
& 'D:\Ruby32-x64\bin\ruby.exe' -rbundler/setup 'D:\Ruby32-x64\lib\ruby\gems\3.2.0\gems\jekyll-4.3.2\exe\jekyll' serve
```

## Notes

`notes/`는 `scripts/build_notes.py`가 생성한다. 원본은 `Zoe-Choi/obsidian_public` 저장소의 `개념/` 노트다. `문서/` 아래 가이드는 올리지 않는다.

```powershell
python scripts/build_notes.py              # GitHub에서 clone 후 빌드
python scripts/build_notes.py --src <dir>  # 로컬 checkout 사용
```

- frontmatter에 `publish: true`가 있는 노트만 빌드
- IP, 내부 호스트명, 자격 증명 패턴이 있으면 빌드 중단
- `index.html`의 `notes:teaser` 마커 사이에 최근 노트 3개를 채운다
