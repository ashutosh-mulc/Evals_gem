'''
1. 현재 파일처럼 해더 없는 YUV420(1920×1088, I420 가정) → PNG
python convert_unknown_images.py ./6 --to png --out ./ --yuv-layout i420 --wh 1920x1088

2. 여러 파일 일괄 변환(표준 이미지 + 일부 raw 혼재)
python convert_unknown_images.py ./inputs_folder --to jpg

3. NV12로 의심될 때
python convert_unknown_images.py ./raw_frames/*.yuv --to png --yuv-layout nv12 --wh 1920x1088
'''

from pathlib import Path
from typing import List, Tuple, Optional
import sys
import argparse

import numpy as np
from PIL import Image, ImageOps

# (선택) HEIC/AVIF 지원
try:
    import pillow_heif  # type: ignore
    pillow_heif.register_heif_opener()
except Exception:
    pass


def is_standard_image(p: Path) -> Tuple[bool, Optional[str], Optional[Tuple[int, int]]]:
    """Pillow가 여는 표준 이미지인지 확인하고 (format, size) 반환."""
    try:
        with Image.open(p) as im:
            im.load()
            return True, im.format, im.size
    except Exception:
        return False, None, None


def guess_yuv420_dims(file_size: int) -> List[Tuple[int, int]]:
    """
    파일 크기로부터 YUV420(1.5 bytes per pixel)의 (w,h) 후보를 추정.
    폭과 높이는 16의 배수로 제한(영상/코덱 정렬 관행 반영).
    """
    candidates = []
    for w in range(256, 8193, 16):
        # size == w*h*3/2  ->  (size*2) % (3*w) == 0  and h integer
        if (file_size * 2) % (3 * w) == 0:
            h = (file_size * 2) // (3 * w)
            if 128 <= h <= 8192 and h % 2 == 0:
                candidates.append((w, h))

    # 흔한 폭/우선순위에 따라 정렬(동률이면 면적 큰 것 우선)
    common_w = [1024, 1920, 3840, 4096, 2560, 2048, 1600, 1536, 1366, 1360,
                1280, 960, 854, 800, 768, 720, 640, 512]
    def score(wh):
        w, h = wh
        rank = common_w.index(w) if w in common_w else 999
        return (rank, -(w * h))
    candidates.sort(key=score)
    return candidates


def yuv420_to_rgb(y: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """
    YUV420(업샘플된 U,V 입력) -> RGB 변환 (BT.601, full range 가정)
    """
    Yf = y.astype(np.float32)
    Uf = u.astype(np.float32) - 128.0
    Vf = v.astype(np.float32) - 128.0
    R = Yf + 1.402 * Vf
    G = Yf - 0.344136 * Uf - 0.714136 * Vf
    B = Yf + 1.772 * Uf
    rgb = np.stack([R, G, B], axis=-1)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def decode_yuv420_file(p: Path, w: int, h: int, layout: str = "i420") -> np.ndarray:
    """
    헤더 없는 단일 프레임 YUV420(8-bit) 파일을 RGB ndarray로 변환.
    layout: i420 (Y U V), yv12 (Y V U), nv12 (Y UV interleaved)
    """
    data = np.fromfile(p, dtype=np.uint8)
    y_size = w * h
    uv = (w // 2) * (h // 2)

    if data.size != y_size + 2 * uv:
        raise ValueError(f"{p.name}: 크기 불일치. 기대값={y_size + 2*uv}, 실제={data.size}")

    Y = data[:y_size].reshape(h, w)

    layout = layout.lower()
    if layout == "i420":
        U = data[y_size : y_size + uv].reshape(h // 2, w // 2)
        V = data[y_size + uv : y_size + 2 * uv].reshape(h // 2, w // 2)
    elif layout == "yv12":
        V = data[y_size : y_size + uv].reshape(h // 2, w // 2)
        U = data[y_size + uv : y_size + 2 * uv].reshape(h // 2, w // 2)
    elif layout == "nv12":
        UV = data[y_size:].reshape(h // 2, w)  # [h/2, w] with interleaved U,V
        U = UV[:, 0::2]
        V = UV[:, 1::2]
    else:
        raise ValueError(f"지원하지 않는 YUV 레이아웃: {layout}")

    # 2x 업샘플(최근접)
    U_up = np.repeat(np.repeat(U, 2, axis=0), 2, axis=1)
    V_up = np.repeat(np.repeat(V, 2, axis=0), 2, axis=1)
    return yuv420_to_rgb(Y, U_up, V_up)


def convert_standard_image(p: Path, out_path: Path, to_ext: str):
    """Pillow로 여는 표준 이미지를 PNG/JPG로 저장."""
    with Image.open(p) as im:
        im = ImageOps.exif_transpose(im)  # EXIF 회전 보정
        if to_ext.lower() in {"jpg", "jpeg"}:
            im = im.convert("RGB")
            im.save(out_path, quality=90, optimize=True)
        else:
            im.save(out_path)


def convert_unknown_file(p: Path,
                         out_dir: Path,
                         to_ext: str = "png",
                         yuv_layout: str = "i420",
                         wh_hint: Optional[str] = None) -> Optional[Path]:
    """
    파일 하나 변환. 성공하면 저장 경로 반환, 실패하면 None.
    - 표준 이미지: Pillow로 변환
    - YUV420 Raw: 해상도 추정 또는 힌트(예: '1920x1088') 사용
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{p.stem}.{to_ext.lower()}"

    # 1) 먼저 표준 이미지 시도
    ok, fmt, _ = is_standard_image(p)
    if ok:
        convert_standard_image(p, out_path, to_ext)
        print(f"[OK] {p.name}: {fmt} → {out_path.name}")
        return out_path

    # 2) Raw YUV420 추정 또는 힌트 사용
    size = p.stat().st_size
    if wh_hint:
        w, h = map(int, wh_hint.lower().split("x"))
        try:
            rgb = decode_yuv420_file(p, w, h, layout=yuv_layout)
            Image.fromarray(rgb).save(out_path)
            print(f"[OK] {p.name}: YUV420({w}x{h},{yuv_layout}) → {out_path.name}")
            return out_path
        except Exception as e:
            print
            print(f"[ERR] {p.name}: {e}")
            return None

    # 힌트 없으면 size로 후보 추정
    cands = guess_yuv420_dims(size)
    if not cands:
        print(f"[SKIP] {p.name}: 표준 이미지도 아니고 YUV420로 추정 불가")
        return None

    # 최우선 후보 1개로 시도 (필요시 사용자가 다른 후보 지정)
    w, h = cands[0]
    try:
        rgb = decode_yuv420_file(p, w, h, layout=yuv_layout)
        Image.fromarray(rgb).save(out_path)
        print(f"[OK] {p.name}: YUV420({w}x{h},{yuv_layout}) 추정 → {out_path.name}")
        return out_path
    except Exception as e:
        print(f"[ERR] {p.name}: {e}")
        print(f"       다른 후보: {', '.join(f'{cw}x{ch}' for cw,ch in cands[1:5])} ...")
        return None


def find_inputs(paths: List[str]) -> List[Path]:
    files: List[Path] = []
    for s in paths:
        p = Path(s)
        if p.is_dir():
            files += [q for q in p.rglob("*") if q.is_file()]
        elif p.is_file():
            files.append(p)
        else:
            # glob 패턴
            files += [q for q in Path().glob(s) if q.is_file()]
    # 중복 제거
    return sorted(set(files))


def main():
    ap = argparse.ArgumentParser(description="알 수 없는 이미지 파일을 PNG/JPG로 변환")
    ap.add_argument("inputs", nargs="+", help="파일/폴더/글롭 패턴(여러 개 가능)")
    ap.add_argument("--to", default="png", choices=["png", "jpg", "jpeg"], help="출력 포맷")
    ap.add_argument("--out", default="converted_out", help="출력 폴더")
    ap.add_argument("--yuv-layout", default="i420", choices=["i420", "nv12", "yv12"], help="Raw YUV 레이아웃")
    ap.add_argument("--wh", help="YUV 해상도 힌트 예) 1920x1088 (미지정 시 파일 크기로 추정)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    files = find_inputs(args.inputs)
    if not files:
        print("입력 파일이 없습니다.")
        sys.exit(1)

    for p in files:
        try:
            convert_unknown_file(
                p,
                out_dir=out_dir,
                to_ext=args.to,
                yuv_layout=args.yuv_layout,
                wh_hint=args.wh,
            )
        except Exception as e:
            print(f"[ERR] {p.name}: {e}")


if __name__ == "__main__":
    main()