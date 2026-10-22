"""Evidence OE3: screenshots from REAL FastAPI + web UI, synthetic data, no external SMTP."""
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

OUT = Path("evidence/oe3").resolve()
OUT.mkdir(parents=True, exist_ok=True)
DB = OUT / "oe3_demonstration.sqlite"
BASE = "http://127.0.0.1:8765"
SHA = os.environ.get("GITHUB_SHA", "CI_SHA_NO_DISPONIBLE")
SCREENSHOTS = {}
OBS = {}
DEMO_PW = "PasswordSynthetic-Only-2026"
env = dict(os.environ)
env.update({
    "DATABASE_URL": "sqlite+pysqlite:///" + str(DB),
    "LOCAL_AUTH_USERNAME": "oe3_admin_demo",
    "LOCAL_AUTH_PASSWORD": DEMO_PW,
    "LOCAL_AUTH_DISPLAY_NAME": "Administración de prueba",
    "SMTP_FERNET_KEY": Fernet.generate_key().decode(),
    "SESSION_SECRET": "CI-local-demo-secret-not-production",
    "AUTH_ENABLED": "true",
    "AUTO_CREATE_TABLES": "true",
    "SEED_ON_STARTUP": "true",
    "SESSION_COOKIE_SECURE": "false",
})
log = open(OUT / "uvicorn_ejecucion.log", "w", encoding="utf-8")
server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                           "--port", "8765"], env=env, stdout=log, stderr=subprocess.STDOUT)

def screenshot(page, code, label):
    page.wait_for_timeout(350)
    path = OUT / f"{code}.png"
    page.screenshot(path=str(path), full_page=True, animations="disabled")
    SCREENSHOTS[code] = {
        "file": path.name, "label": label, "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source": "Chromium Playwright / navegador ejecutando FastAPI real, datos ficticios",
    }

def request_json(context, method, path, payload=None):
    kwargs = {"data": payload} if payload is not None else {}
    response = context.request.fetch(BASE + path, method=method, **kwargs)
    try: data = response.json()
    except Exception: data = response.text()
    return response.status, data

def text_dialog(page, text):
    page.locator("#requestText").fill(text)
    page.locator("#analyzeBtn").click()
    page.wait_for_timeout(500)

def add_fake_user():
    # Mismo fichero SQLite, una sesión administrativa de prueba crea un usuario de prueba independiente.
    os.environ.update({k: env[k] for k in [
        "DATABASE_URL", "SESSION_SECRET", "SMTP_FERNET_KEY"]})
    from app.db.session import SessionLocal
    from app.models.domain import LocalUser
    from app.services.auth import hash_password
    from sqlalchemy import select
    with SessionLocal() as db:
        if db.scalar(select(LocalUser).where(LocalUser.username == "oe3_usuario_b")) is None:
            db.add(LocalUser(username="oe3_usuario_b", display_name="Usuario B (prueba)",
                             role="USUARIO_FINAL", active=True, password_hash=hash_password(DEMO_PW)))
            db.commit()

def build_fichas():
    metadata = {
        "E03-01":("Titularidad y aislamiento entre usuarios", "Captura de inicio de sesión + trazas HTTP 200/404 + test de tres sesiones", ["01_login", "02_inicio"], "PARCIAL: HTTP acreditado en CI; captura de acceso legítimo"),
        "E03-02":("Roles administrativos", "Catálogo con sesión administrativa y respuestas HTTP 403 del usuario final", ["09_catalogo"], "PARCIAL: rol probado; permiso de importación acreditado en test"),
        "E03-03":("Variante es-CR y atributos", "Prueba S09 y captura de análisis de solicitud es-CR", ["03_ambiguedad"], "ACREDITADO por prueba; captura es ejemplo real del estado de validación"),
        "E03-04":("Ambigüedad y aclaración", "«compus» sin tipo definido y pregunta activa", ["03_ambiguedad"], "EVIDENCIA VISUAL + trazabilidad de prueba"),
        "E03-05":("Control negativo no comercial", "Resultado de prueba automática del control negativo, sin captura representativa", [], "PENDIENTE: integrar prueba negativa explícita"),
        "E03-06":("Varios artículos y cantidades", "Captura de análisis, estructura de dos artículos y prueba S05", ["04_varios_articulos","05_detalle"], "ACREDITADO en conjunto acotado"),
        "E03-07":("Respuesta que completa dos atributos", "Interacción con RAM y SSD y prueba automatizada multiatributo", ["06_validacion_resuelta"], "ACREDITADO en el caso de regresión"),
        "E03-08":("Unidades y proveedores compatibles", "Pantalla de solicitudes a proveedor y consultas de compatibilidad", ["07_preparacion","08_borradores"], "PARCIAL: unidad por defecto; falta prueba exhaustiva de unidades específicas"),
        "E03-09":("Correo bajo autorización", "Pantallas de edición y aprobación + prueba SMTP falso sin correo real", ["08_borradores","10_autorizacion"], "ACREDITADO con SMTP SIMULADO"),
        "E03-10":("Credenciales SMTP individuales", "Prueba de cifrado y lectura segregada de cuenta; no exponer clave en imagen", [], "ACREDITADO en pruebas con cifrado y SMTP falso; sin servidor externo"),
        "E03-11":("Migración PostgreSQL 16", "Registro de job postgres-migration, script SQL y test de FK", [], "ACREDITADO en PostgreSQL efímero CI, NO en BD local persistente"),
        "E03-12":("Trazabilidad metodológica", "Matriz S01–S16 + reportes ejecutados de CI y estado de S17–S20", [], "PARCIAL: S17–S20 permanecen por realizar"),
    }
    d = Document()
    sec = d.sections[0]
    sec.top_margin = Inches(.72);sec.bottom_margin=Inches(.68)
    sec.left_margin=Inches(.78);sec.right_margin=Inches(.78)
    d.styles["Normal"].font.name="Times New Roman";d.styles["Normal"].font.size=Pt(10.5)
    h=d.add_heading("FICHAS INDIVIDUALES DE EVIDENCIA — OE3",0)
    d.add_paragraph("Prueba de concepto de PLN para la estructuración de solicitudes de proformas")
    d.add_paragraph("Registro de captura real de navegador contra la aplicación web en ejecución; datos exclusivamente ficticios.")
    d.add_paragraph(f"Commit: {SHA}   |   Fecha UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}")
    d.add_paragraph("Estas capturas son evidencia de interfaz. Las verificaciones de permisos, persistencia y SMTP se respaldan en pruebas automatizadas, no en imágenes.")
    for idx,(case,(name,proof,images,state)) in enumerate(metadata.items()):
        d.add_page_break()
        d.add_heading(f"{case} — {name}",level=1)
        for label,value in [("Componente","OE3 — procesamiento, validación y emisión controlada"),
                            ("Entrada/condición",proof),("Resultado",state),
                            ("Ambiente","CI aislado; SQLite para la interfaz, PostgreSQL 16 en trabajo independiente; SMTP simulado"),
                            ("Trazabilidad",f"Commit {SHA}; GitHub Actions; tests/test_oe3_regresion.py, tests/test_oe3_http.py y tests/test_oe3_scenarios.py")]:
            p=d.add_paragraph();p.add_run(label+": ").bold=True;p.add_run(value)
        if images:
            for image in images[:2]:
                if image in SCREENSHOTS:
                    d.add_paragraph(f"Captura: {SCREENSHOTS[image]['label']}")
                    d.add_picture(str(OUT / SCREENSHOTS[image]["file"]),width=Inches(5.7))
                    d.add_paragraph(f"SHA-256: {SCREENSHOTS[image]['sha256']}")
                else:
                    d.add_paragraph(f"Captura {image}: NO CAPTURADA — no se presenta sustituto.")
        else:
            d.add_paragraph("Sin captura aplicable: utilizar el resultado técnico enlazado y el registro ejecutado. No se inventa una pantalla.")
    d.add_page_break()
    d.add_heading("Rastreo externo verificable",level=1)
    d.add_paragraph("Pruebas S01–S16 + regresiones: https://github.com/AndreaCarrilloOp/PLN-Proformas/actions")
    d.add_paragraph("Migración: tests/test_oe3_postgresql.py y migrations/manual_oe3_20261022.sql.")
    d.add_paragraph("Las evidencias del flujo S17–S20 pertenecen a la evaluación integrada y no se declaran completadas.")
    out=OUT/"Fichas_Evidencia_OE3_Ejecucion_Real.docx"
    d.save(out)
    return str(out)

try:
    for _ in range(75):
        try:
            if urllib.request.urlopen(BASE+"/health", timeout=1).status==200:
                break
        except Exception: pass
        if server.poll() is not None:raise RuntimeError("El servidor FastAPI terminó: consultar uvicorn_ejecucion.log")
        time.sleep(.35)
    else:raise RuntimeError("FastAPI no inició")
    add_fake_user()
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=["--no-sandbox"])
        ctx=browser.new_context(viewport={"width":1440,"height":900},device_scale_factor=1,
                                locale="es-CR",accept_downloads=False)
        page=ctx.new_page()
        page.goto(BASE+"/login",wait_until="networkidle")
        screenshot(page,"01_login","Pantalla real de autenticación, sin credenciales capturadas")
        page.locator("#username").fill("oe3_admin_demo")
        page.locator("#password").fill(DEMO_PW)
        page.locator("#loginBtn").click()
        page.wait_for_url(BASE+"/",timeout=15000)
        page.wait_for_timeout(500)
        screenshot(page,"02_inicio","Interfaz autenticada; solicitud inicial vacía")

        text_dialog(page,"Ocupo cinco compus con 16 GB RAM")
        page.get_by_text("Entendí la solicitud.",exact=False).wait_for(timeout=10000)
        screenshot(page,"03_ambiguedad","Ambigüedad regional identificada por PLN con pregunta activa")
        status,arr=request_json(ctx,"GET","/api/solicitudes/buscar?q=Ocupo")
        OBS["ambiguedad"]={"http":status,"requests_found":len(arr) if isinstance(arr,list) else 0}
        page.locator("#newRequestBtn").click()
        page.wait_for_timeout(250)

        text_dialog(page,"2 laptops Dell y 3 monitores Samsung")
        page.get_by_text("Entendí la solicitud.",exact=False).wait_for(timeout=10000)
        screenshot(page,"04_varios_articulos","Análisis real de solicitud con dos artículos separados")
        page.locator('[data-screen="validation"]').first.evaluate("(el)=>el.click()") if page.locator('[data-screen="validation"]').count() else page.evaluate('showScreen("validation")')
        screenshot(page,"05_detalle","Vista de artículos, cantidades y campos faltantes por artículo")
        page.evaluate('showScreen("request")')
        req_id = page.evaluate("currentRequest && currentRequest.id")
        if not req_id: raise RuntimeError("No se pudo resolver el ID real de la solicitud")
        # Aclaraciones por la interfaz de chat (sin inyectar resultados).
        maxsteps=9
        for i in range(maxsteps):
            request=page.evaluate("currentRequest")
            if request["estado"]=="COMPLETO":break
            nexttask=page.evaluate("getValidationTasks(currentRequest)[0]")
            if nexttask is None:raise RuntimeError("Solicitud incompleta sin pregunta")
            key=nexttask["data"]["field_key"] if nexttask["type"]=="question" else nexttask["data"]["field_name"]
            if nexttask["type"]=="confirmation":
                answer="sí"
            else:
                answer={"ram":"16 GB RAM y 512 GB SSD","almacenamiento":"512 GB SSD",
                        "tamano_pantalla":"24 pulgadas","cantidad":"2","producto":"Laptop"}.get(key)
                if not answer:raise RuntimeError("Pregunta sin respuesta de demostración: "+str(key))
            text_dialog(page,answer)
        completed=page.evaluate("currentRequest")
        OBS["solicitud"]={"id":req_id,"estado":completed["estado"],
                          "articulos":[{"producto":it["producto"],"cantidad":str(it["cantidad"]),
                                      "estado":it["estado"]} for it in completed["articulos"]]}
        screenshot(page,"06_validacion_resuelta","Conversación con validación guiada completada, sin preguntas repetidas")
        if completed["estado"]!="COMPLETO":raise RuntimeError("El flujo no quedó COMPLETO: "+str(OBS["solicitud"]))

        page.evaluate('showScreen("providers")')
        screenshot(page,"07_preparacion","Pantalla real de preparación de solicitudes por proveedor")
        page.locator("#providersBtn").click()
        page.locator("#emailDraftList .mail-list-item").first.wait_for(timeout=12000)
        screenshot(page,"08_borradores","Borradores dirigidos únicamente a proveedores compatibles")
        page.locator("#goToApprovalBtn").click()
        page.locator("#emailApprovalList .approval-mail-card").first.wait_for(timeout=12000)
        screenshot(page,"09_aprobacion_previa","Etapa de autorización explícita antes de enviar")
        page.locator("#emailApprovalList .authorize-action").first.click()
        page.wait_for_timeout(350)
        screenshot(page,"10_autorizacion","Correo aprobado por acción de la persona usuaria; no se envió")
        status,arr=request_json(ctx,"GET",f"/api/solicitudes/{req_id}/correos")
        OBS["correos"]={"http":status,"count":len(arr) if isinstance(arr,list) else 0,
                        "states":[it.get("estado") for it in arr] if isinstance(arr,list) else []}
        page.locator('[data-screen="catalog"]').first.click()
        page.wait_for_timeout(450)
        screenshot(page,"11_catalogo","Catálogo en la interfaz autenticada con datos de prueba")

        bctx=browser.new_context(viewport={"width":1440,"height":900})
        bpage=bctx.new_page()
        bpage.goto(BASE+"/login")
        bpage.locator("#username").fill("oe3_usuario_b")
        bpage.locator("#password").fill(DEMO_PW)
        bpage.locator("#loginBtn").click()
        bpage.wait_for_url(BASE+"/",timeout=15000)
        status,_=request_json(bctx,"GET",f"/api/solicitudes/{req_id}")
        status_import,_=request_json(bctx,"POST","/api/catalogo/importar?tipo=proveedores")
        OBS["aislamiento"]={"acceso_ajeno_http":status,"importacion_usuario_http":status_import,
                            "criterio_acceso":status==404,"criterio_rol":status_import==403}
        bctx.close();ctx.close();browser.close()
finally:
    server.terminate()
    try:server.wait(timeout=8)
    except subprocess.TimeoutExpired:server.kill()
    log.close()

manifest={"created_utc":datetime.now(timezone.utc).isoformat(),"commit":SHA,
          "method":"Playwright Chromium screenshots of unmodified repo frontend with running FastAPI",
          "database":"isolated disposable SQLite, demo seed, no production data",
          "smtp":"no real sending; screenshot covers pre-send approval only",
          "observations":OBS,"screenshots":SCREENSHOTS}
(OUT/"manifest_evidencias.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
build_fichas()
print(json.dumps({"screenshot_count":len(SCREENSHOTS),"screenshots":list(SCREENSHOTS),
                 "observations":OBS,"document":"Fichas_Evidencia_OE3_Ejecucion_Real.docx"},ensure_ascii=False))
