"""MinerU 在线 API（https://mineru.net，见官方 Precision Extract 文档）。"""

from __future__ import annotations

import io
import json
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pypdf import PdfReader, PdfWriter

from app.config import settings
from app.pipeline_logging import clip, plog_info
from app.services.pdf_parse import sha256_file


class MinerUCloudError(Exception):
    pass


def _base_url() -> str:
    return (settings.mineru_api_base_url or "https://mineru.net").rstrip("/")


def _headers() -> dict[str, str]:
    token = (settings.mineru_api_token or "").strip()
    if not token:
        raise MinerUCloudError("未配置 MINERU_API_TOKEN，请在 apps/api/.env 中设置（见 https://mineru.net/apiManage/docs）")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "*/*",
    }


def _api_json(resp: httpx.Response) -> dict:
    resp.raise_for_status()
    body = resp.json()
    if not isinstance(body, dict):
        raise MinerUCloudError(f"无效响应: {clip(str(body), 500)}")
    if body.get("code") != 0:
        raise MinerUCloudError(body.get("msg") or f"MinerU API 错误 code={body.get('code')}")
    data = body.get("data")
    if not isinstance(data, dict):
        raise MinerUCloudError("响应缺少 data")
    return data


def _upload_and_submit(client: httpx.Client, pdf_path: Path, paper_id: str) -> str:
    """申请上传 URL、上传 PDF，返回 batch_id。"""
    model = (settings.mineru_cloud_model_version or "vlm").strip() or "vlm"
    payload = {
        "files": [{"name": pdf_path.name, "data_id": paper_id[:128]}],
        "model_version": model,
    }
    plog_info("parse", "MinerU 云端申请上传 name=%s data_id=%s", pdf_path.name, paper_id[:8])
    data = _api_json(client.post(f"{_base_url()}/api/v4/file-urls/batch", headers=_headers(), json=payload))
    batch_id = data.get("batch_id")
    urls = data.get("file_urls")
    if not batch_id or not urls or not isinstance(urls, list):
        raise MinerUCloudError("未返回 batch_id 或 file_urls")
    upload_url = urls[0]
    with pdf_path.open("rb") as f:
        up = client.put(upload_url, content=f.read(), timeout=600.0)
    if up.status_code != 200:
        raise MinerUCloudError(f"上传 PDF 失败 HTTP {up.status_code}: {clip(up.text, 400)}")
    plog_info("parse", "MinerU 云端上传完成 batch_id=%s", batch_id)
    return str(batch_id)


def _poll_batch_done(client: httpx.Client, batch_id: str, file_name: str) -> str:
    """轮询批量任务，返回 full_zip_url。"""
    deadline = time.monotonic() + float(settings.parse_timeout_sec)
    interval = max(2.0, float(settings.mineru_cloud_poll_interval_sec))
    url = f"{_base_url()}/api/v4/extract-results/batch/{batch_id}"

    while time.monotonic() < deadline:
        data = _api_json(client.get(url, headers=_headers(), timeout=60.0))
        results = data.get("extract_result")
        if not isinstance(results, list):
            time.sleep(interval)
            continue
        item = None
        for r in results:
            if not isinstance(r, dict):
                continue
            if r.get("file_name") == file_name:
                item = r
                break
        if item is None and len(results) == 1:
            item = results[0]
        if not item:
            time.sleep(interval)
            continue

        state = (item.get("state") or "").lower()
        if state == "done":
            zip_url = item.get("full_zip_url")
            if not zip_url:
                raise MinerUCloudError("任务完成但无 full_zip_url")
            return str(zip_url)
        if state == "failed":
            raise MinerUCloudError(item.get("err_msg") or "MinerU 云端解析失败")
        plog_info(
            "parse",
            "MinerU 云端任务进行中 state=%s progress=%s（total_pages 为当前上传文件页数；分段解析时每段单独计数）",
            state,
            item.get("extract_progress"),
        )
        time.sleep(interval)

    raise MinerUCloudError(f"MinerU 云端解析超时（>{settings.parse_timeout_sec}s）")


_ZIP_DOWNLOAD_RETRIES = 4


def _download_mineru_zip_bytes(client: httpx.Client, zip_url: str) -> bytes:
    """
    下载解析结果 zip。full_zip_url 常指向第三方 CDN，偶发 DNS 失败（如 nodename nor servname）；
    对连接类错误重试，最终抛出 MinerUCloudError 以便上层 pypdf 降级而非 ASGI 500。
    """
    hint = ""
    try:
        pr = urlparse(zip_url)
        if pr.netloc:
            hint = f"（{pr.scheme}://{pr.netloc}）"
    except Exception:
        pass

    last: BaseException | None = None
    for attempt in range(_ZIP_DOWNLOAD_RETRIES):
        try:
            zr = client.get(zip_url, timeout=600.0)
            zr.raise_for_status()
            return zr.content
        except httpx.HTTPStatusError as e:
            raise MinerUCloudError(
                f"下载 MinerU 结果 zip HTTP {e.response.status_code}{hint}: {clip(e.response.text, 300)}"
            ) from e
        except (
            httpx.ConnectError,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.RemoteProtocolError,
        ) as e:
            last = e
            plog_info(
                "parse",
                "下载结果 zip 失败（尝试 %s/%s）%s: %s",
                attempt + 1,
                _ZIP_DOWNLOAD_RETRIES,
                hint or "",
                e,
            )
            if attempt + 1 < _ZIP_DOWNLOAD_RETRIES:
                time.sleep(min(2.0 * (2**attempt), 30.0))
    raise MinerUCloudError(
        f"下载 MinerU 结果 zip 失败（已重试 {_ZIP_DOWNLOAD_RETRIES} 次）{hint}。"
        f"多为 CDN 域名解析失败或网络波动；可检查 DNS/代理/VPN 后重试索引。"
        f" 最后一次错误: {last}"
    ) from last


def _markdown_from_zip(zip_bytes: bytes, out_dir: Path) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        md_name = None
        for prefer in ("full.md", "document.md"):
            for n in names:
                if n.endswith(prefer) or n.split("/")[-1].lower() == prefer:
                    md_name = n
                    break
            if md_name:
                break
        if not md_name:
            mds = [n for n in names if n.lower().endswith(".md")]
            if not mds:
                raise MinerUCloudError("结果 zip 中未找到 Markdown")
            md_name = max(mds, key=lambda n: zf.getinfo(n).file_size)

        md = zf.read(md_name).decode("utf-8", errors="replace")
        (out_dir / "document.md").write_text(md, encoding="utf-8")

        for n in names:
            if n == md_name:
                continue
            target = out_dir / Path(n)
            if n.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(n))
    return md


def _pdf_page_count(pdf_path: Path) -> int:
    reader = PdfReader(str(pdf_path))
    return len(reader.pages)


def _is_cloud_page_limit_error(exc: MinerUCloudError) -> bool:
    s = str(exc).lower()
    if "page" not in s:
        return False
    return "limit" in s or "exceed" in s or "200" in s


def _split_md_url(rest: str) -> tuple[str, str]:
    """Markdown 链接 (url) 或 (url "title") 拆出 url 与可选 title 段。"""
    rest = rest.strip()
    if len(rest) >= 3 and rest.endswith('"') and ' "' in rest:
        ix = rest.rfind(' "')
        if ix > 0:
            return rest[:ix].strip(), rest[ix:]
    return rest, ""


def _prefix_relative_asset_urls(md: str, url_prefix: str) -> str:
    """合并多段 MinerU 结果时，为相对资源路径加上分段子目录前缀。"""
    url_prefix = url_prefix.strip("/") + "/"
    pref_lower = url_prefix.lower()

    def is_non_relative(u: str) -> bool:
        u = u.strip()
        if not u:
            return True
        if re.match(r"^[a-z][a-z0-9+.-]*:", u, re.I):
            return True
        if u.startswith(("#", "mailto:", "javascript:", "data:")):
            return True
        return False

    def should_prefix(u: str) -> bool:
        if is_non_relative(u):
            return False
        core = u.lstrip("./")
        if core.lower().startswith(pref_lower):
            return False
        cl = core.lower()
        hints = ("images/", "figures/", "auto/", "image/", "/images/")
        if any(h in cl for h in hints):
            return True
        base = cl.split("?", 1)[0]
        return base.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp"))

    def fix_url(u: str) -> str:
        u = u.strip()
        if not should_prefix(u):
            return u
        inner = u[2:] if u.startswith("./") else u
        return f"{url_prefix}{inner}"

    def repl_bang(m: re.Match[str]) -> str:
        alt, rest = m.group(1), m.group(2)
        url_part, title = _split_md_url(rest)
        nu = fix_url(url_part)
        if nu == url_part:
            return m.group(0)
        return f"![{alt}]({nu}{title})"

    out = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", repl_bang, md)

    def repl_img(m: re.Match[str]) -> str:
        pre, quote, u, q2 = m.group(1), m.group(2), m.group(3), m.group(4)
        nu = fix_url(u)
        if nu == u:
            return m.group(0)
        return f"{pre}{quote}{nu}{q2}"

    out = re.sub(
        r'(<img\s[^>]*\bsrc\s*=\s*)(["\'])([^"\']+)(\2)',
        repl_img,
        out,
        flags=re.I,
    )
    return out


_CHUNK_PROGRESS_VERSION = 1


def _chunk_progress_path(chunks_root: Path) -> Path:
    return chunks_root / "_progress.json"


def _read_chunk_progress(chunks_root: Path) -> dict | None:
    p = _chunk_progress_path(chunks_root)
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_chunk_progress(chunks_root: Path, data: dict) -> None:
    chunks_root.mkdir(parents=True, exist_ok=True)
    _chunk_progress_path(chunks_root).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _infer_completed_chunks_from_disk(chunks_root: Path, num_chunks: int) -> set[int]:
    """从 000/document.md 起连续推断已成功解析的切片下标（无 _progress.json 时的兜底）。"""
    done: set[int] = set()
    for ci in range(num_chunks):
        p = chunks_root / f"{ci:03d}" / "document.md"
        if not p.is_file():
            break
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            break
        if len(text.strip()) < 100:
            break
        done.add(ci)
    return done


def _normalize_completed_prefix(completed: set[int], num_chunks: int) -> set[int]:
    """断点只承认从 0 起连续成功的前缀，避免空洞。"""
    if not completed:
        return set()
    out: set[int] = set()
    for i in range(num_chunks):
        if i not in completed:
            break
        out.add(i)
    return out


def _parse_pdf_via_cloud_chunked(
    pdf_path: Path,
    paper_id: str,
    out_dir: Path,
    *,
    force_reparse: bool = False,
    pdf_sha256: str | None = None,
) -> tuple[str, dict]:
    max_p = int(settings.mineru_cloud_max_pages_per_chunk)
    chunks_root = out_dir / "_mineru_cloud_chunks"

    reader = PdfReader(str(pdf_path))
    n = len(reader.pages)
    if n == 0:
        raise MinerUCloudError("PDF 无页面")

    try:
        sha = (pdf_sha256 or "").strip() or sha256_file(pdf_path)
    except Exception as ex:
        raise MinerUCloudError(f"无法计算 PDF sha256（断点续传需要）: {ex}") from ex

    stem = pdf_path.stem[:80] or "doc"
    num_chunks = (n + max_p - 1) // max_p

    completed: set[int] = set()
    if force_reparse:
        shutil.rmtree(chunks_root, ignore_errors=True)
        plog_info("parse", "MinerU 云端分段：force=true，已清除旧切片与断点状态")
    else:
        prog = _read_chunk_progress(chunks_root)
        ok = (
            prog
            and int(prog.get("version", 0)) == _CHUNK_PROGRESS_VERSION
            and prog.get("pdf_sha256") == sha
            and int(prog.get("n", -1)) == n
            and int(prog.get("max_p", -1)) == max_p
        )
        if ok:
            raw = prog.get("completed") or []
            for x in raw:
                if type(x) is int:
                    completed.add(x)
                elif isinstance(x, str) and x.isdigit():
                    completed.add(int(x))
            completed = {c for c in completed if 0 <= c < num_chunks}
        elif chunks_root.is_dir():
            inferred = _infer_completed_chunks_from_disk(chunks_root, num_chunks)
            if inferred:
                completed = inferred
                _write_chunk_progress(
                    chunks_root,
                    {
                        "version": _CHUNK_PROGRESS_VERSION,
                        "pdf_sha256": sha,
                        "n": n,
                        "max_p": max_p,
                        "completed": sorted(completed),
                    },
                )
                plog_info(
                    "parse",
                    "MinerU 云端分段：无有效 _progress.json，已从磁盘推断已完成切片 %s",
                    sorted(completed),
                )
            else:
                shutil.rmtree(chunks_root, ignore_errors=True)

    # 校验已标记完成的切片目录确有 Markdown，并规范为连续前缀
    for ci in list(completed):
        p = chunks_root / f"{ci:03d}" / "document.md"
        if not p.is_file() or len(p.read_text(encoding="utf-8", errors="replace").strip()) < 100:
            completed.discard(ci)
            shutil.rmtree(chunks_root / f"{ci:03d}", ignore_errors=True)
    completed = _normalize_completed_prefix(completed, num_chunks)

    chunks_root.mkdir(parents=True, exist_ok=True)

    plog_info(
        "parse",
        "MinerU 云端分段：原 PDF 未修改；共 %s 页，拆 %s 段（每段最多 %s 页）。"
        "MinerU 日志里 total_pages 仅为当前切片。断点：将跳过已完成前 %s 段。",
        n,
        num_chunks,
        max_p,
        len(completed),
    )
    meta: dict = {
        "mode": "mineru_cloud_chunked",
        "mineru": True,
        "mineru_api_base": _base_url(),
        "paper_id": paper_id,
        "mineru_pages_total": n,
        "mineru_cloud_chunk_size": max_p,
        "mineru_cloud_chunk_count": num_chunks,
        "mineru_cloud_resume_chunks": sorted(completed),
    }
    md_parts: list[str] = []

    with tempfile.TemporaryDirectory(prefix="mineru_pdf_chunks_") as tmp:
        tmp_path = Path(tmp)
        for ci in range(num_chunks):
            p0 = ci * max_p
            p1 = min((ci + 1) * max_p, n)
            chunk_pages = p1 - p0
            chunk_out = chunks_root / f"{ci:03d}"
            rel_prefix = f"_mineru_cloud_chunks/{ci:03d}"

            if ci in completed:
                md_disk = chunk_out / "document.md"
                md_i = md_disk.read_text(encoding="utf-8", errors="replace")
                plog_info(
                    "parse",
                    "MinerU 云端分段 %s/%s：断点续传，跳过云端解析（原书第 %s–%s 页）",
                    ci + 1,
                    num_chunks,
                    p0 + 1,
                    p1,
                )
            else:
                writer = PdfWriter()
                try:
                    writer.append(reader, pages=(p0, p1))
                except Exception as ex:
                    plog_info("parse", "切片 append 失败，回退逐页 add_page: %s", ex)
                    writer = PdfWriter()
                    for pi in range(p0, p1):
                        writer.add_page(reader.pages[pi])
                safe_name = f"{stem}_p{p0 + 1}-{p1}_part{ci + 1:03d}.pdf"
                chunk_file = tmp_path / safe_name
                with chunk_file.open("wb") as f:
                    writer.write(f)

                got = len(PdfReader(str(chunk_file)).pages)
                if got != chunk_pages:
                    raise MinerUCloudError(
                        f"PDF 切片页数异常：本段应为原书第 {p0 + 1}–{p1} 页（共 {chunk_pages} 页），"
                        f"写出后 pypdf 读到 {got} 页。原文件未改写，请检查 PDF 是否损坏或换用 MinerU CLI。"
                    )
                plog_info(
                    "parse",
                    "MinerU 云端分段 %s/%s：上传临时切片 %s 页（原书第 %s–%s 页）",
                    ci + 1,
                    num_chunks,
                    chunk_pages,
                    p0 + 1,
                    p1,
                )

                chunk_out.mkdir(parents=True, exist_ok=True)
                chunk_id = f"{paper_id}_c{ci}"
                md_i, part_meta = parse_pdf_via_cloud(chunk_file, chunk_id, chunk_out)
                if part_meta.get("mineru_batch_id"):
                    meta[f"mineru_batch_id_c{ci}"] = part_meta["mineru_batch_id"]

                completed.add(ci)
                _write_chunk_progress(
                    chunks_root,
                    {
                        "version": _CHUNK_PROGRESS_VERSION,
                        "pdf_sha256": sha,
                        "n": n,
                        "max_p": max_p,
                        "completed": sorted(completed),
                    },
                )

            md_parts.append(
                f"## 原书页码 第 {p0 + 1}–{p1} 页 · 分段 {ci + 1}/{num_chunks}\n\n"
                + _prefix_relative_asset_urls(md_i, rel_prefix)
            )

    full_md = "\n\n---\n\n".join(md_parts)
    (out_dir / "document.md").write_text(full_md, encoding="utf-8")
    try:
        _chunk_progress_path(chunks_root).unlink(missing_ok=True)
    except OSError:
        pass
    plog_info(
        "parse",
        "MinerU 云端分段解析完成 chunks=%s pages=%s md_chars=%s",
        num_chunks,
        n,
        len(full_md),
    )
    return full_md, meta


def parse_pdf_via_cloud_with_splitting(
    pdf_path: Path,
    paper_id: str,
    out_dir: Path,
    *,
    force_reparse: bool = False,
    pdf_sha256: str | None = None,
) -> tuple[str, dict]:
    """
    云端解析：未超页数则整份上传；超过 MINERU_CLOUD_MAX_PAGES_PER_CHUNK 时先用 pypdf 切片再合并结果。
    若整份上传返回页数限制错误，也会自动改为切片重试。
    分段模式支持断点续传（勿与 force 同用清空缓存）。
    """
    max_p = int(settings.mineru_cloud_max_pages_per_chunk)
    n: int | None = None
    try:
        n = _pdf_page_count(pdf_path)
    except Exception as ex:
        plog_info("parse", "无法读取 PDF 页数，将先尝试整份上传 MinerU 云端: %s", ex)

    if n is not None and n > max_p:
        plog_info(
            "parse",
            "PDF 页数=%s 超过云端单文件上限=%s，将切片解析后合并",
            n,
            max_p,
        )
        return _parse_pdf_via_cloud_chunked(
            pdf_path,
            paper_id,
            out_dir,
            force_reparse=force_reparse,
            pdf_sha256=pdf_sha256,
        )

    try:
        return parse_pdf_via_cloud(pdf_path, paper_id, out_dir)
    except MinerUCloudError as e:
        if _is_cloud_page_limit_error(e):
            plog_info("parse", "MinerU 云端页数限制，改为切片解析: %s", e)
            return _parse_pdf_via_cloud_chunked(
                pdf_path,
                paper_id,
                out_dir,
                force_reparse=force_reparse,
                pdf_sha256=pdf_sha256,
            )
        raise


def parse_pdf_via_cloud(pdf_path: Path, paper_id: str, out_dir: Path) -> tuple[str, dict]:
    """
    通过 MinerU 在线 API 解析本地 PDF，写入 out_dir/document.md。
    文档：https://mineru.net/doc/docs/index_en/
    """
    meta: dict = {
        "mode": "mineru_cloud",
        "mineru": True,
        "mineru_api_base": _base_url(),
        "paper_id": paper_id,
    }
    timeout = httpx.Timeout(600.0, connect=30.0)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            batch_id = _upload_and_submit(client, pdf_path, paper_id)
            meta["mineru_batch_id"] = batch_id
            zip_url = _poll_batch_done(client, batch_id, pdf_path.name)
            meta["mineru_zip_url"] = zip_url
            plog_info("parse", "MinerU 云端下载结果 zip")
            zip_bytes = _download_mineru_zip_bytes(client, zip_url)
            md = _markdown_from_zip(zip_bytes, out_dir)
    except MinerUCloudError:
        raise
    except httpx.HTTPStatusError as e:
        raise MinerUCloudError(
            f"MinerU 云端 HTTP {e.response.status_code}: {clip(e.response.text, 500)}"
        ) from e
    except httpx.RequestError as e:
        raise MinerUCloudError(f"MinerU 云端网络错误: {e}") from e
    plog_info("parse", "MinerU 云端完成 md_chars=%s", len(md))
    return md, meta
