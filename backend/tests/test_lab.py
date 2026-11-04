"""Title & Thumbnail Lab: critérios explicados, imagens hostis, isolamento e limites declarados."""
from __future__ import annotations

import io
import json
import random
import struct
import zlib

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app import main
from app.config import Settings
from app.db import utcnow
from app.intel import lab
from app.studio import store

TOKEN = "segredo-de-teste"
HEADERS = {"X-YTI-Token": TOKEN}


@pytest.fixture
def cfg(tmp_path):
    return Settings(mode="demo", data_dir=tmp_path, api_token=TOKEN)


@pytest.fixture
def studio(cfg):
    conn = store.open_studio(cfg)
    store.seed_demo_once(conn)
    yield conn
    conn.close()


def png(image: Image.Image, fmt: str = "PNG", **options) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, fmt, **options)
    return buffer.getvalue()


def flat(color=(128, 128, 128), size=(1280, 720)) -> bytes:
    return png(Image.new("RGB", size, color))


def focal(size=(1280, 720)) -> bytes:
    """Fundo escuro com um único bloco claro e saturado, à direita."""
    image = Image.new("RGB", size, (15, 20, 40))
    ImageDraw.Draw(image).rectangle((size[0] * 0.7, size[1] * 0.35, size[0] * 0.92, size[1] * 0.65), fill=(255, 210, 0))
    return png(image)


def noise(size=(1280, 720)) -> bytes:
    rng = random.Random(7)
    image = Image.new("RGB", size)
    image.putdata([(rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255)) for _ in range(size[0] * size[1])])
    return png(image)


def score(evaluation: dict, key: str) -> int:
    return next(c["score"] for c in evaluation["criteria"] if c["key"] == key)


# --- Títulos --------------------------------------------------------------------------------------

def test_title_note_never_claims_prediction():
    data = lab.evaluate_title("Por que Roma caiu?", "queda de Roma")
    assert "não prevê CTR" in data["note"] and not {"ctr", "predicted_ctr", "viral"} & set(data)
    assert all(c["explanation"] for c in data["criteria"])


def test_length_rules():
    assert score(lab.evaluate_title("x" * 60), "tamanho") == 100
    long_title = lab.evaluate_title("palavra " * 12)
    assert score(long_title, "tamanho") < 100 and any("cortado" in w for w in long_title["warnings"])
    assert any("até 100" in w for w in lab.evaluate_title("x" * 101)["warnings"])


def test_clarity_penalizes_caps_and_symbols():
    assert score(lab.evaluate_title("O DIA QUE ROMA CAIU!!!"), "clareza") < score(lab.evaluate_title("O dia em que Roma caiu"), "clareza")


def test_curiosity_and_promise_are_detected():
    assert score(lab.evaluate_title("Por que Roma caiu?"), "curiosidade") > score(lab.evaluate_title("Roma antiga"), "curiosidade")
    assert score(lab.evaluate_title("3 fatos sobre Roma"), "promessa") > score(lab.evaluate_title("Roma antiga"), "promessa")


def test_subject_consistency():
    match = lab.evaluate_title("A queda de Roma", "queda de Roma")
    miss = lab.evaluate_title("Vikings no gelo", "queda de Roma")
    assert score(match, "assunto") == 100 and score(miss, "assunto") == 0
    assert any("não menciona" in w for w in miss["warnings"])
    assert "assunto" not in {c["key"] for c in lab.evaluate_title("Vikings no gelo")["criteria"]}


def test_exaggeration_gets_a_warning():
    assert any("exagerada" in w for w in lab.evaluate_title("Você não vai acreditar em Roma")["warnings"])


@pytest.mark.parametrize("title", ["", "   "])
def test_empty_title_is_refused(title):
    with pytest.raises(store.StudioError):
        lab.evaluate_title(title)


def test_suggestions_follow_language_and_skip_copies():
    pt = lab.suggest_titles("queda de Roma", "pt")
    assert len(pt) == 3 and len({s["title"] for s in pt}) == 3 and pt[0]["title"] == "Queda de Roma: do começo ao fim"
    assert all(s["why"] and s["review_score"] is not None for s in pt)
    assert "start to finish" in lab.suggest_titles("fall of Rome", "en")[0]["title"]
    assert "de principio a fin" in lab.suggest_titles("caída de Roma", "es")[0]["title"]
    forbidden = {"queda de roma: do comeco ao fim"}
    other = lab.suggest_titles("queda de Roma", "pt", forbidden)
    assert len(other) == 3 and all("do começo ao fim" not in s["title"] for s in other)
    with pytest.raises(store.StudioError):
        lab.suggest_titles("x")


# --- Imagens --------------------------------------------------------------------------------------

def test_flat_image_scores_low_on_contrast_and_hierarchy():
    _image, data = lab.analyze_image(flat())
    assert score(data, "contraste") == 0 and score(data, "hierarquia") == 20 and score(data, "complexidade") == 35
    assert data["width"] == 1280 and data["warnings"] == []


def test_focal_image_scores_better_and_reports_position():
    _image, data = lab.analyze_image(focal())
    _image, plain = lab.analyze_image(flat())
    assert score(data, "contraste") > score(plain, "contraste")
    assert score(data, "hierarquia") > score(plain, "hierarquia")
    assert score(data, "legibilidade") > score(plain, "legibilidade")
    assert "à direita" in next(c for c in data["criteria"] if c["key"] == "hierarquia")["explanation"]


def test_noise_is_marked_as_too_busy():
    _image, data = lab.analyze_image(noise((640, 360)))
    assert score(data, "complexidade") < 60 and "ruído" in next(c for c in data["criteria"] if c["key"] == "complexidade")["explanation"]


def test_dark_and_bright_images_are_flagged():
    _i, dark = lab.analyze_image(flat((5, 5, 5)))
    _i, bright = lab.analyze_image(flat((250, 250, 250)))
    assert "Escura" in next(c for c in dark["criteria"] if c["key"] == "brilho")["explanation"]
    assert "Clara" in next(c for c in bright["criteria"] if c["key"] == "brilho")["explanation"]


def test_size_and_ratio_warnings():
    _i, small = lab.analyze_image(flat(size=(320, 180)))
    assert any("Resolução" in w for w in small["warnings"])
    _i, square = lab.analyze_image(flat(size=(1280, 1280)))
    assert any("16:9" in w for w in square["warnings"]) and score(square, "proporcao") < 100


def test_limits_are_declared():
    _image, data = lab.analyze_image(flat())
    assert "Não lê texto na imagem." in data["limits"] and "não prevê CTR" in data["note"]


@pytest.mark.parametrize("fmt", ["JPEG", "WEBP", "PNG"])
def test_accepted_formats(fmt):
    image, data = lab.analyze_image(png(Image.new("RGB", (1280, 720), (10, 90, 200)), fmt))
    assert data["format"] == fmt and image.mode == "RGB" and image.width <= lab.ANALYSIS_WIDTH


@pytest.mark.parametrize("data,code", [
    (b"", "invalid_image"), (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "invalid_image"), (b"nao sou imagem" * 50, "invalid_image"),
    (b"\x89PNG\r\n\x1a\n" + b"\x00" * 40, "invalid_image"),
])
def test_invalid_files_are_refused(data, code):
    with pytest.raises(store.StudioError) as error:
        lab.analyze_image(data)
    assert error.value.code == code


def test_other_image_formats_are_refused():
    with pytest.raises(store.StudioError) as error:
        lab.analyze_image(png(Image.new("RGB", (10, 10)), "GIF"))
    assert error.value.code == "invalid_image"


def test_oversized_file_is_refused_before_decoding():
    with pytest.raises(store.StudioError) as error:
        lab.analyze_image(b"0" * (lab.MAX_IMAGE_BYTES + 1))
    assert error.value.code == "image_too_large"


def test_decompression_bomb_is_refused():
    """PNG de poucos bytes que declara 60 mil x 60 mil pixels."""
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    header = struct.pack(">IIBBBBB", 60000, 60000, 8, 0, 0, 0, 0)
    bomb = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"\x00" * 100)) + chunk(b"IEND", b"")
    with pytest.raises(store.StudioError) as error:
        lab.analyze_image(bomb)
    assert error.value.code in {"image_too_large", "invalid_image"}


def test_saved_copy_drops_metadata(studio, cfg, tmp_path):
    project = lab.create_project(studio, "chn_demo_cronicas", "Queda de Roma", None, utcnow())
    variation = lab.add_variation(studio, "chn_demo_cronicas", project["id"], "A queda de Roma", "", utcnow())
    source = Image.new("RGB", (1280, 720), (10, 90, 200))
    exif = Image.Exif()
    exif[0x010e] = "dado privado"
    saved = lab.attach_image(studio, cfg, "chn_demo_cronicas", variation["id"], png(source, "JPEG", exif=exif), utcnow())
    path = lab.image_path(studio, cfg, "chn_demo_cronicas", saved["image_file"])
    assert path.is_file() and b"dado privado" not in path.read_bytes() and saved["image_eval"]["criteria"]


# --- Projetos e isolamento ------------------------------------------------------------------------

def test_project_flow_saves_and_compares_variations(studio):
    project = lab.create_project(studio, "chn_demo_cronicas", "Queda de Roma", None, utcnow())
    first = lab.add_variation(studio, "chn_demo_cronicas", project["id"], "A queda de Roma", "Direto", utcnow())
    second = lab.add_variation(studio, "chn_demo_cronicas", project["id"], "Por que Roma caiu?", "", utcnow())
    lab.update_variation(studio, "chn_demo_cronicas", second["id"], note="Abre pergunta", favorite=True, now=utcnow())
    data = lab.get_project(studio, "chn_demo_cronicas", project["id"])
    assert [v["id"] for v in data["variations"]] == [second["id"], first["id"]] and data["variations"][0]["note"] == "Abre pergunta"
    assert data["suggestions"] and "não prevê CTR" in data["note"]
    assert lab.list_projects(studio, "chn_demo_cronicas")["items"][0]["variations"] == 2


def test_lab_is_isolated_by_channel(studio, cfg):
    project = lab.create_project(studio, "chn_demo_cronicas", "Queda de Roma", None, utcnow())
    variation = lab.add_variation(studio, "chn_demo_cronicas", project["id"], "A queda de Roma", "", utcnow())
    saved = lab.attach_image(studio, cfg, "chn_demo_cronicas", variation["id"], focal(), utcnow())
    assert lab.list_projects(studio, "chn_demo_rotas")["total"] == 0
    for call in (lambda: lab.get_project(studio, "chn_demo_rotas", project["id"]),
                 lambda: lab.add_variation(studio, "chn_demo_rotas", project["id"], "x y z", "", utcnow()),
                 lambda: lab.attach_image(studio, cfg, "chn_demo_rotas", variation["id"], focal(), utcnow()),
                 lambda: lab.update_variation(studio, "chn_demo_rotas", variation["id"], note="x", favorite=None, now=utcnow()),
                 lambda: lab.delete_variation(studio, cfg, "chn_demo_rotas", variation["id"]),
                 lambda: lab.delete_project(studio, cfg, "chn_demo_rotas", project["id"]),
                 lambda: lab.image_path(studio, cfg, "chn_demo_rotas", saved["image_file"])):
        with pytest.raises(store.StudioError) as error:
            call()
        assert error.value.status == 404


@pytest.mark.parametrize("name", ["..\\..\\.api_token", "../../.api_token", "var_x.jpg", "var_0123456789abcdef.png", ".api_token", "var_0123456789abcdef.jpg"])
def test_image_path_refuses_traversal_and_unknown_names(studio, cfg, name):
    (cfg.data_dir / ".api_token").write_text("segredo", encoding="ascii")
    with pytest.raises(store.StudioError) as error:
        lab.image_path(studio, cfg, "chn_demo_cronicas", name)
    assert error.value.status == 404


def test_recommendation_must_belong_to_the_channel(studio):
    other = store.create_channel(studio, {"name": "Outro", "formats": ["long"]})
    studio.execute(
        "INSERT INTO recommendations (id, channel_id, dedupe_key, subject, justification, sources_json, titles_json, thumbnail_idea, hook, format, duration_seconds, target_audience, editorial_priority, data_basis, origin, created_at, updated_at) "
        "VALUES ('rec_x', ?, 'k', 's', 'j', '[]', '[]', 't', 'h', 'long', 60, 'a', 'media', 'editorial', 'regras', 'x', 'x')", (other["id"],))
    studio.commit()
    with pytest.raises(store.StudioError) as error:
        lab.create_project(studio, "chn_demo_cronicas", "Assunto bom", "rec_x", utcnow())
    assert error.value.code == "recommendation_not_in_channel"


def test_deleting_removes_files(studio, cfg):
    project = lab.create_project(studio, "chn_demo_cronicas", "Queda de Roma", None, utcnow())
    one = lab.add_variation(studio, "chn_demo_cronicas", project["id"], "Título um", "", utcnow())
    two = lab.add_variation(studio, "chn_demo_cronicas", project["id"], "Título dois", "", utcnow())
    path_one = lab.image_path(studio, cfg, "chn_demo_cronicas", lab.attach_image(studio, cfg, "chn_demo_cronicas", one["id"], focal(), utcnow())["image_file"])
    path_two = lab.image_path(studio, cfg, "chn_demo_cronicas", lab.attach_image(studio, cfg, "chn_demo_cronicas", two["id"], focal(), utcnow())["image_file"])
    lab.delete_variation(studio, cfg, "chn_demo_cronicas", one["id"])
    assert not path_one.exists() and path_two.exists()
    lab.delete_project(studio, cfg, "chn_demo_cronicas", project["id"])
    assert not path_two.exists()


def test_stored_evaluation_is_json_without_paths(studio, cfg):
    project = lab.create_project(studio, "chn_demo_cronicas", "Queda de Roma", None, utcnow())
    variation = lab.add_variation(studio, "chn_demo_cronicas", project["id"], "Título", "", utcnow())
    saved = lab.attach_image(studio, cfg, "chn_demo_cronicas", variation["id"], focal(), utcnow())
    assert str(cfg.data_dir) not in json.dumps(saved, ensure_ascii=False)


# --- API ------------------------------------------------------------------------------------------

@pytest.fixture
def api(cfg):
    main.app.dependency_overrides[main.settings_dep] = lambda: cfg
    yield TestClient(main.app, base_url="http://127.0.0.1")
    main.app.dependency_overrides.clear()


def test_api_full_flow_with_upload_and_token(api, cfg):
    base = "/api/intel/channels/chn_demo_cronicas/lab"
    assert api.post(f"{base}/projects", json={"subject": "Queda de Roma"}).status_code == 401
    project = api.post(f"{base}/projects", json={"subject": "Queda de Roma"}, headers=HEADERS).json()
    variation = api.post(f"{base}/projects/{project['id']}/variations", json={"title": "A queda de Roma"}, headers=HEADERS).json()
    upload = f"{base}/variations/{variation['id']}/image"
    assert api.post(upload, content=focal()).status_code == 401
    assert api.post(upload, content=b"lixo", headers=HEADERS).status_code == 415
    assert api.post(upload, content=b"0" * (lab.MAX_IMAGE_BYTES + 1), headers=HEADERS).status_code == 413
    saved = api.post(upload, content=focal(), headers=HEADERS)
    assert saved.status_code == 200 and saved.json()["image_eval"]["review_score"] >= 0
    picture = api.get(f"{base}/images/{saved.json()['image_file']}")
    assert picture.status_code == 200 and picture.headers["content-type"] == "image/jpeg" and picture.headers["x-content-type-options"] == "nosniff"
    assert api.get(f"/api/intel/channels/chn_demo_rotas/lab/images/{saved.json()['image_file']}").status_code == 404
    assert api.get(f"{base}/projects/{project['id']}").json()["variations"][0]["id"] == variation["id"]
    assert api.get(f"/api/intel/channels/chn_demo_rotas/lab/projects/{project['id']}").status_code == 404
    assert api.post("/api/intel/lab/evaluate", json={"title": "Por que Roma caiu?", "subject": "Roma"}, headers=HEADERS).json()["review_score"] > 0
    assert api.post(f"{base}/variations/{variation['id']}/update", json={"favorite": True}, headers=HEADERS).json()["favorite"] is True
    assert api.post(f"{base}/variations/{variation['id']}/delete", headers=HEADERS).status_code == 200
    assert api.post(f"{base}/projects/{project['id']}/delete", headers=HEADERS).status_code == 200


def test_lab_suggestions_drop_collected_titles(api):
    base = "/api/intel/channels/chn_demo_cronicas/lab"
    project = api.post(f"{base}/projects", json={"subject": "Roma antiga"}, headers=HEADERS).json()
    from app.db import connect

    settings = main.app.dependency_overrides[main.settings_dep]()
    conn = connect(settings.db_path)
    conn.execute("UPDATE videos SET title = 'Roma antiga: do começo ao fim' WHERE id = (SELECT id FROM videos LIMIT 1)")
    conn.commit()
    conn.close()
    titles = [s["title"] for s in api.get(f"{base}/projects/{project['id']}").json()["suggestions"]]
    assert "Roma antiga: do começo ao fim" not in titles and titles


def test_deleting_channel_removes_lab_images(api, cfg):
    base = "/api/intel/channels/chn_demo_imperios/lab"
    project = api.post(f"{base}/projects", json={"subject": "Tenochtitlan"}, headers=HEADERS).json()
    variation = api.post(f"{base}/projects/{project['id']}/variations", json={"title": "Um título"}, headers=HEADERS).json()
    api.post(f"{base}/variations/{variation['id']}/image", content=focal(), headers=HEADERS)
    assert (cfg.data_dir / "lab" / "chn_demo_imperios").exists()
    assert api.post("/api/studio/channels/chn_demo_imperios/delete", json={"confirm_name": store.DEMO_CHANNELS[2]["name"]}, headers=HEADERS).status_code == 200
    assert not (cfg.data_dir / "lab" / "chn_demo_imperios").exists()
