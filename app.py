# ============================================================
# IMPORTS
# ============================================================

import asyncio
import shutil
import sys
import tempfile
import threading
import time

from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import streamlit as st

from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


# ============================================================
# WINDOWS CONFIG
# ต้องอยู่ก่อนเริ่มใช้งาน Playwright
# ============================================================

if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsProactorEventLoopPolicy()
    )


# ============================================================
# CONFIG
# ============================================================

LOGIN_URL = "https://ams.cpall.co.th/login.action"

HEADLESS = True

DEFAULT_TIMEOUT = 30_000
LOGIN_TIMEOUT = 60_000
POPUP_TIMEOUT = 60_000
DOWNLOAD_TIMEOUT = 120_000

BANGKOK_TIMEZONE = ZoneInfo("Asia/Bangkok")


# ============================================================
# SELECTORS
# ============================================================

USERNAME_SELECTOR = (
    '#username:visible, '
    'input[name="username"]:visible, '
    'input[name="j_username"]:visible, '
    'input[type="text"]:visible'
)

PASSWORD_SELECTOR = (
    '#password:visible, '
    'input[name="password"]:visible, '
    'input[name="j_password"]:visible, '
    'input[type="password"]:visible'
)

LOGIN_BUTTON_SELECTOR = (
    'button.button-login:visible, '
    'button:has-text("Login"):visible, '
    'input[value="Login"]:visible'
)

LOGIN_SUCCESS_SELECTOR = "#actionLocCode"

LOADING_POPUP_SELECTOR = "#ui-datepicker-div"

BRANCH_CODE_SELECTOR = "#actionLocCode"

BRANCH_SEARCH_SELECTOR = (
    'img.input-icon'
    '[onclick*="searchPopupCostCenter"]'
    '[onclick*="actionLocCode"]'
)

STATUS_SELECTOR = "#statusId"
STATUS_ALL_VALUE = " "

CHECKBOX_SELECTOR = "#isActive"

SEARCH_BUTTON_SELECTOR = (
    'input.button-login'
    '[type="button"]'
    '[value="ค้นหา"]'
)

EXPORT_BUTTON_SELECTOR = (
    'input.button-login'
    '[type="button"]'
    '[value="Export to excel"]'
)


# ============================================================
# CUSTOM ERROR
# ============================================================

class RPAExecutionError(RuntimeError):
    def __init__(
        self,
        message,
        screenshot=None,
    ):
        super().__init__(message)
        self.screenshot = screenshot


# ============================================================
# REAL-TIME LOGGER
# ============================================================

class RpaLogger:
    def __init__(self, placeholder):
        self.placeholder = placeholder
        self.lines = []
        self.started_at = time.perf_counter()

    def log(
        self,
        message,
        level="INFO",
    ):
        current_time = datetime.now(
            BANGKOK_TIMEZONE
        ).strftime("%H:%M:%S")

        elapsed = (
            time.perf_counter()
            - self.started_at
        )

        line = (
            f"[{current_time}] "
            f"[+{elapsed:07.2f}s] "
            f"[{level}] "
            f"{message}"
        )

        self.lines.append(line)

        st.session_state.rpa_logs = (
            self.lines.copy()
        )

        self.render()

    def render(self):
        self.placeholder.code(
            "\n".join(self.lines),
            language="text",
        )

    def start_step(self, message):
        self.log(
            f"เริ่ม: {message}",
            "STEP",
        )

        return time.perf_counter()

    def finish_step(
        self,
        message,
        started_at,
    ):
        duration = (
            time.perf_counter()
            - started_at
        )

        self.log(
            f"สำเร็จ: {message} "
            f"(ใช้เวลา {duration:.2f} วินาที)",
            "OK",
        )

    def fail_step(
        self,
        message,
        started_at,
    ):
        duration = (
            time.perf_counter()
            - started_at
        )

        self.log(
            f"ไม่สำเร็จ: {message} "
            f"(ใช้เวลา {duration:.2f} วินาที)",
            "ERROR",
        )


# ============================================================
# PREVENT MULTIPLE RPA JOBS
# ป้องกันบัญชีกลางทำงานซ้อนกัน
# ============================================================

@st.cache_resource
def get_rpa_lock():
    return threading.Lock()


# ============================================================
# PAGE INFORMATION
# ============================================================

def get_safe_url(page):
    try:
        url = page.url
        parsed = urlsplit(url)

        # ตัด Query String และ Fragment
        # เพื่อไม่ให้ Token ติดมากับ Log
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                "",
                "",
            )
        )

    except Exception:
        return "ไม่สามารถอ่าน URL ได้"


def get_page_title(page):
    try:
        return page.title()

    except Exception:
        return "ไม่สามารถอ่าน Page title ได้"


def get_page_text(page, max_length=800):
    try:
        body_text = page.locator(
            "body"
        ).inner_text(
            timeout=5_000
        )

        body_text = " ".join(
            body_text.split()
        )

        return body_text[:max_length]

    except Exception:
        return "ไม่สามารถอ่านข้อความบนหน้าเว็บได้"


# ============================================================
# LAUNCH BROWSER
# ============================================================

def launch_browser(
    playwright,
    logger,
):
    chromium_path = (
        shutil.which("chromium")
        or shutil.which("chromium-browser")
        or shutil.which("google-chrome")
        or shutil.which("google-chrome-stable")
    )

    launch_options = {
        "headless": HEADLESS,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-extensions",
        ],
    }

    if chromium_path:
        logger.log(
            f"พบ Chromium: {chromium_path}"
        )

        launch_options["executable_path"] = (
            chromium_path
        )

    else:
        logger.log(
            "ไม่พบ System Chromium "
            "กำลังทดลองใช้ Browser ของ Playwright",
            "WARN",
        )

    return playwright.chromium.launch(
        **launch_options
    )


# ============================================================
# WAIT FOR POPUP
# ============================================================

def wait_for_popup_hidden(
    page,
    logger,
):
    popup = page.locator(
        LOADING_POPUP_SELECTOR
    ).first

    if popup.count() == 0:
        logger.log(
            "ไม่พบ Loading popup "
            "จึงดำเนินการขั้นตอนถัดไป"
        )
        return

    try:
        if popup.is_visible():
            logger.log(
                "พบ Loading popup "
                "กำลังรอให้โหลดข้อมูลเสร็จ"
            )

            popup.wait_for(
                state="hidden",
                timeout=POPUP_TIMEOUT,
            )

            logger.log(
                "Loading popup ปิดแล้ว"
            )

        else:
            logger.log(
                "Loading popup ไม่ได้แสดงอยู่"
            )

    except PlaywrightTimeoutError:
        raise RuntimeError(
            "Loading popup ไม่หายภายใน "
            f"{POPUP_TIMEOUT // 1000} วินาที"
        )


# ============================================================
# LOGIN
# ============================================================

def login_ams(
    page,
    username,
    password,
    logger,
):
    step_started = logger.start_step(
        "เข้าสู่ระบบ AMS"
    )

    try:
        logger.log(
            "กำลังเปิดเว็บไซต์ AMS"
        )

        response = page.goto(
            LOGIN_URL,
            wait_until="domcontentloaded",
            timeout=LOGIN_TIMEOUT,
        )

        if response:
            logger.log(
                f"เว็บไซต์ตอบกลับ HTTP "
                f"{response.status}"
            )

        page.wait_for_timeout(3_000)

        logger.log(
            f"URL ปัจจุบัน: "
            f"{get_safe_url(page)}"
        )

        logger.log(
            f"Page title: "
            f"{get_page_title(page)}"
        )

        username_input = page.locator(
            USERNAME_SELECTOR
        ).first

        password_input = page.locator(
            PASSWORD_SELECTOR
        ).first

        logger.log(
            "กำลังตรวจหาช่อง Username "
            "และ Password"
        )

        try:
            username_input.wait_for(
                state="visible",
                timeout=LOGIN_TIMEOUT,
            )

            password_input.wait_for(
                state="visible",
                timeout=LOGIN_TIMEOUT,
            )

        except PlaywrightTimeoutError:
            raise RuntimeError(
                "ไม่พบช่อง Username หรือ Password"
                f" | URL: {get_safe_url(page)}"
                f" | Page title: "
                f"{get_page_title(page)}"
                f" | ข้อความบนหน้าเว็บ: "
                f"{get_page_text(page)}"
            )

        logger.log(
            "พบช่อง Username และ Password"
        )

        # ไม่แสดง Username และ Password ลงใน Log
        username_input.click()
        username_input.fill("")
        username_input.type(
            username,
            delay=100,
        )

        password_input.click()
        password_input.fill("")
        password_input.type(
            password,
            delay=100,
        )

        if not username_input.input_value():
            raise RuntimeError(
                "Username ไม่ถูกกรอกลงในเว็บไซต์"
            )

        if not password_input.input_value():
            raise RuntimeError(
                "Password ไม่ถูกกรอกลงในเว็บไซต์"
            )

        logger.log(
            "กรอก Username และ Password แล้ว"
        )

        login_button = page.locator(
            LOGIN_BUTTON_SELECTOR
        ).first

        login_button.wait_for(
            state="visible",
            timeout=LOGIN_TIMEOUT,
        )

        logger.log(
            "กำลังกดปุ่ม Login"
        )

        login_button.click()

        logger.log(
            "กดปุ่ม Login แล้ว "
            "กำลังรอหน้าค้นหา"
        )

        try:
            page.locator(
                LOGIN_SUCCESS_SELECTOR
            ).first.wait_for(
                state="visible",
                timeout=LOGIN_TIMEOUT,
            )

        except PlaywrightTimeoutError:
            raise RuntimeError(
                "กด Login แล้ว "
                "แต่ไม่พบหน้าค้นหา"
                f" | URL: {get_safe_url(page)}"
                f" | Page title: "
                f"{get_page_title(page)}"
                f" | ข้อความบนหน้าเว็บ: "
                f"{get_page_text(page)}"
            )

        logger.log(
            "เข้าสู่ระบบ AMS สำเร็จ"
        )

        wait_for_popup_hidden(
            page=page,
            logger=logger,
        )

        logger.finish_step(
            "เข้าสู่ระบบ AMS",
            step_started,
        )

    except Exception:
        logger.fail_step(
            "เข้าสู่ระบบ AMS",
            step_started,
        )
        raise


# ============================================================
# SEARCH
# ============================================================

def search_documents(
    page,
    branch_code,
    search_delay,
    logger,
):
    step_started = logger.start_step(
        "ค้นหาเอกสาร"
    )

    try:
        branch_input = page.locator(
            BRANCH_CODE_SELECTOR
        ).first

        logger.log(
            "กำลังตรวจหาช่องรหัสสาขา"
        )

        branch_input.wait_for(
            state="visible",
            timeout=DEFAULT_TIMEOUT,
        )

        branch_input.click()
        branch_input.fill("")
        branch_input.type(
            branch_code,
            delay=100,
        )

        branch_input.press("Tab")

        actual_branch_code = (
            branch_input.input_value().strip()
        )

        if actual_branch_code != branch_code:
            raise RuntimeError(
                "รหัสสาขาที่กรอกไม่ตรงกับ "
                "ค่าที่กำหนด"
            )

        logger.log(
            "กรอกรหัสสาขาเรียบร้อยแล้ว"
        )

        branch_search = page.locator(
            BRANCH_SEARCH_SELECTOR
        ).first

        branch_search.wait_for(
            state="visible",
            timeout=DEFAULT_TIMEOUT,
        )

        logger.log(
            "กำลังกดปุ่มค้นหารหัสสาขา"
        )

        branch_search.click()

        page.wait_for_timeout(2_000)

        wait_for_popup_hidden(
            page=page,
            logger=logger,
        )

        logger.log(
            "กำลังเลือกสถานะ: ทั้งหมด"
        )

        status_dropdown = page.locator(
            STATUS_SELECTOR
        ).first

        status_dropdown.wait_for(
            state="visible",
            timeout=DEFAULT_TIMEOUT,
        )

        status_dropdown.select_option(
            value=STATUS_ALL_VALUE
        )

        logger.log(
            "เลือกสถานะทั้งหมดเรียบร้อยแล้ว"
        )

        checkbox = page.locator(
            CHECKBOX_SELECTOR
        ).first

        checkbox.wait_for(
            state="visible",
            timeout=DEFAULT_TIMEOUT,
        )

        if checkbox.is_checked():
            logger.log(
                "Checkbox ถูกเลือกอยู่ "
                "กำลังยกเลิกการเลือก"
            )

            checkbox.uncheck()

        else:
            logger.log(
                "Checkbox ไม่ได้ถูกเลือกอยู่แล้ว"
            )

        if checkbox.is_checked():
            raise RuntimeError(
                "ไม่สามารถยกเลิก Checkbox ได้"
            )

        search_button = page.locator(
            SEARCH_BUTTON_SELECTOR
        ).first

        search_button.wait_for(
            state="visible",
            timeout=DEFAULT_TIMEOUT,
        )

        logger.log(
            "กำลังกดปุ่มค้นหาเอกสาร"
        )

        search_button.click()

        logger.log(
            "กดปุ่มค้นหาแล้ว "
            f"กำลังรอ {search_delay} วินาที "
            "ก่อน Export"
        )

        delay_started = time.perf_counter()

        page.wait_for_timeout(
            search_delay * 1_000
        )

        delay_duration = (
            time.perf_counter()
            - delay_started
        )

        logger.log(
            "ครบระยะเวลารอหลัง Search "
            f"({delay_duration:.2f} วินาที)"
        )

        wait_for_popup_hidden(
            page=page,
            logger=logger,
        )

        logger.finish_step(
            "ค้นหาเอกสาร",
            step_started,
        )

    except Exception:
        logger.fail_step(
            "ค้นหาเอกสาร",
            step_started,
        )
        raise


# ============================================================
# EXPORT EXCEL
# ============================================================

def export_excel(
    page,
    logger,
):
    step_started = logger.start_step(
        "Export ข้อมูลเป็น Excel"
    )

    try:
        export_folder = Path(
            tempfile.mkdtemp(
                prefix="ams_exports_"
            )
        )

        logger.log(
            "สร้างพื้นที่ชั่วคราวสำหรับ "
            "จัดเก็บไฟล์แล้ว"
        )

        export_button = page.locator(
            EXPORT_BUTTON_SELECTOR
        ).first

        export_button.wait_for(
            state="visible",
            timeout=DEFAULT_TIMEOUT,
        )

        logger.log(
            "กำลังกดปุ่ม Export to excel"
        )

        with page.expect_download(
            timeout=DOWNLOAD_TIMEOUT
        ) as download_info:
            export_button.click()

        logger.log(
            "เว็บไซต์เริ่มส่งไฟล์แล้ว"
        )

        download = download_info.value

        original_filename = Path(
            download.suggested_filename
        )

        timestamp = datetime.now(
            BANGKOK_TIMEZONE
        ).strftime("%Y%m%d_%H%M%S")

        extension = (
            original_filename.suffix
            or ".xlsx"
        )

        filename = (
            f"{original_filename.stem}_"
            f"{timestamp}"
            f"{extension}"
        )

        save_path = (
            export_folder / filename
        )

        logger.log(
            "กำลังบันทึกไฟล์ที่ดาวน์โหลด"
        )

        download.save_as(
            str(save_path)
        )

        if not save_path.exists():
            raise RuntimeError(
                "Download สำเร็จ "
                "แต่ไม่พบไฟล์ที่บันทึก"
            )

        file_size = save_path.stat().st_size

        if file_size == 0:
            raise RuntimeError(
                "ไฟล์ที่ Download "
                "มีขนาด 0 byte"
            )

        file_size_mb = (
            file_size / 1024 / 1024
        )

        logger.log(
            f"ดาวน์โหลดไฟล์สำเร็จ: "
            f"{filename}"
        )

        logger.log(
            f"ขนาดไฟล์: "
            f"{file_size_mb:.2f} MB"
        )

        logger.finish_step(
            "Export ข้อมูลเป็น Excel",
            step_started,
        )

        return save_path

    except Exception:
        logger.fail_step(
            "Export ข้อมูลเป็น Excel",
            step_started,
        )
        raise


# ============================================================
# RUN RPA
# ============================================================

def run_rpa(
    username,
    password,
    branch_code,
    search_delay,
    logger,
):
    total_started = time.perf_counter()

    playwright_instance = None
    browser = None
    context = None
    page = None

    completed = False
    dialog_messages = []

    logger.log(
        "เริ่มต้นกระบวนการ RPA",
        "START",
    )

    try:
        browser_started = logger.start_step(
            "เปิด Chromium"
        )

        playwright_instance = (
            sync_playwright().start()
        )

        browser = launch_browser(
            playwright=playwright_instance,
            logger=logger,
        )

        context = browser.new_context(
            viewport={
                "width": 1440,
                "height": 900,
            },
            ignore_https_errors=True,
            accept_downloads=True,
        )

        page = context.new_page()

        page.set_default_timeout(
            DEFAULT_TIMEOUT
        )

        def handle_dialog(dialog):
            message = dialog.message

            dialog_messages.append(
                message
            )

            logger.log(
                f"เว็บไซต์แสดงข้อความ: "
                f"{message}",
                "DIALOG",
            )

            dialog.accept()

        page.on(
            "dialog",
            handle_dialog,
        )

        logger.finish_step(
            "เปิด Chromium",
            browser_started,
        )

        login_ams(
            page=page,
            username=username,
            password=password,
            logger=logger,
        )

        search_documents(
            page=page,
            branch_code=branch_code,
            search_delay=search_delay,
            logger=logger,
        )

        output_file = export_excel(
            page=page,
            logger=logger,
        )

        completed = True

        return output_file

    except Exception as error:
        logger.log(
            f"RPA หยุดทำงาน: {error}",
            "ERROR",
        )

        screenshot = None

        if page is not None:
            logger.log(
                f"URL ตอนเกิด Error: "
                f"{get_safe_url(page)}",
                "DEBUG",
            )

            logger.log(
                f"Page title ตอนเกิด Error: "
                f"{get_page_title(page)}",
                "DEBUG",
            )

            try:
                screenshot = page.screenshot(
                    full_page=True
                )

                logger.log(
                    "บันทึกภาพหน้าจอตอนเกิด "
                    "Error สำเร็จ",
                    "DEBUG",
                )

            except Exception as screenshot_error:
                logger.log(
                    "ไม่สามารถบันทึกภาพหน้าจอได้: "
                    f"{screenshot_error}",
                    "WARN",
                )

        error_message = str(error)

        if dialog_messages:
            error_message += (
                " | ข้อความล่าสุดจากเว็บไซต์: "
                f"{dialog_messages[-1]}"
            )

        raise RPAExecutionError(
            message=error_message,
            screenshot=screenshot,
        ) from error

    finally:
        logger.log(
            "กำลังปิด Browser"
        )

        if context is not None:
            try:
                context.close()
            except Exception:
                pass

        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass

        if playwright_instance is not None:
            try:
                playwright_instance.stop()
            except Exception:
                pass

        total_duration = (
            time.perf_counter()
            - total_started
        )

        if completed:
            logger.log(
                "RPA ทำงานเสร็จสมบูรณ์ "
                f"ใช้เวลารวม "
                f"{total_duration:.2f} วินาที",
                "COMPLETE",
            )

        else:
            logger.log(
                "RPA ทำงานไม่สำเร็จ "
                f"ใช้เวลารวม "
                f"{total_duration:.2f} วินาที",
                "FAILED",
            )


# ============================================================
# FILE MIME TYPE
# ============================================================

def get_excel_mime(filename):
    filename = filename.lower()

    if filename.endswith(".xls"):
        return "application/vnd.ms-excel"

    return (
        "application/vnd.openxmlformats-"
        "officedocument.spreadsheetml.sheet"
    )


# ============================================================
# STREAMLIT UI
# ============================================================

st.set_page_config(
    page_title="AMS Document Export",
    page_icon="📄",
    layout="centered",
)

st.title("AMS Document Export")

st.caption(
    "Login → Search → Export Excel"
)

st.info(
    "Username และ Password "
    "ใช้เฉพาะระหว่างการทำงานครั้งนี้ "
    "และจะไม่ถูกบันทึกลงใน Log"
)


# ============================================================
# SESSION STATE
# ============================================================

if "download_data" not in st.session_state:
    st.session_state.download_data = None

if "download_filename" not in st.session_state:
    st.session_state.download_filename = None

if "rpa_logs" not in st.session_state:
    st.session_state.rpa_logs = []

if "debug_image" not in st.session_state:
    st.session_state.debug_image = None


# ============================================================
# INPUT FORM
# ============================================================

with st.form(
    "ams_form",
    clear_on_submit=True,
):
    username = st.text_input(
        "Username",
        placeholder="กรอก Username",
    )

    password = st.text_input(
        "Password",
        type="password",
        placeholder="กรอก Password",
    )

    branch_code = st.text_input(
        "รหัสสาขา",
        placeholder="กรอกรหัสสาขา",
    )

    search_delay = st.number_input(
        "ระยะเวลารอหลัง Search "
        "ก่อน Export (วินาที)",
        min_value=0,
        max_value=600,
        value=30,
        step=5,
    )

    submitted = st.form_submit_button(
        "ค้นหาและ Export",
        type="primary",
        use_container_width=True,
    )


# ============================================================
# LOG DISPLAY
# ============================================================

st.subheader("สถานะการทำงาน")

log_placeholder = st.empty()

if st.session_state.rpa_logs:
    log_placeholder.code(
        "\n".join(
            st.session_state.rpa_logs
        ),
        language="text",
    )

else:
    log_placeholder.info(
        "ระบบยังไม่ได้เริ่มทำงาน"
    )


# ============================================================
# SUBMIT PROCESS
# ============================================================

if submitted:
    st.session_state.download_data = None
    st.session_state.download_filename = None
    st.session_state.debug_image = None
    st.session_state.rpa_logs = []

    logger = RpaLogger(
        placeholder=log_placeholder
    )

    if not username.strip():
        st.error(
            "กรุณากรอก Username"
        )

    elif not password:
        st.error(
            "กรุณากรอก Password"
        )

    elif not branch_code.strip():
        st.error(
            "กรุณากรอกรหัสสาขา"
        )

    else:
        rpa_lock = get_rpa_lock()

        lock_acquired = rpa_lock.acquire(
            blocking=False
        )

        if not lock_acquired:
            st.warning(
                "ขณะนี้มีผู้ใช้งาน RPA อยู่ "
                "กรุณารอให้งานก่อนหน้าเสร็จ "
                "แล้วลองใหม่อีกครั้ง"
            )

        else:
            try:
                logger.log(
                    "ระบบรับคำขอเรียบร้อยแล้ว"
                )

                with st.spinner(
                    "RPA กำลังทำงาน "
                    "โปรดติดตามรายละเอียดใน Log..."
                ):
                    output_file = run_rpa(
                        username=username.strip(),
                        password=password,
                        branch_code=(
                            branch_code.strip()
                        ),
                        search_delay=int(
                            search_delay
                        ),
                        logger=logger,
                    )

                    logger.log(
                        "กำลังนำไฟล์เข้าสู่ "
                        "หน้าดาวน์โหลด"
                    )

                    st.session_state.download_data = (
                        output_file.read_bytes()
                    )

                    st.session_state.download_filename = (
                        output_file.name
                    )

                    # ลบไฟล์ชั่วคราวหลังอ่านเข้า Memory
                    try:
                        shutil.rmtree(
                            output_file.parent,
                            ignore_errors=True,
                        )

                        logger.log(
                            "ลบไฟล์ชั่วคราว "
                            "ออกจาก Server แล้ว"
                        )

                    except Exception as cleanup_error:
                        logger.log(
                            "ไม่สามารถลบไฟล์ชั่วคราวได้: "
                            f"{cleanup_error}",
                            "WARN",
                        )

                st.success(
                    "Export ข้อมูลสำเร็จ"
                )

            except RPAExecutionError as error:
                st.error(
                    f"RPA ทำงานไม่สำเร็จ: "
                    f"{error}"
                )

                if error.screenshot:
                    st.session_state.debug_image = (
                        error.screenshot
                    )

            except Exception as error:
                logger.log(
                    f"เกิดข้อผิดพลาดจากระบบ: "
                    f"{error}",
                    "ERROR",
                )

                st.error(
                    f"เกิดข้อผิดพลาดจากระบบ: "
                    f"{error}"
                )

            finally:
                rpa_lock.release()


# ============================================================
# DOWNLOAD RESULT
# ============================================================

if (
    st.session_state.download_data
    and st.session_state.download_filename
):
    st.download_button(
        label="ดาวน์โหลดไฟล์ Excel",
        data=st.session_state.download_data,
        file_name=(
            st.session_state.download_filename
        ),
        mime=get_excel_mime(
            st.session_state.download_filename
        ),
        type="primary",
        use_container_width=True,
    )


# ============================================================
# DEBUG SCREENSHOT
# ============================================================

if st.session_state.debug_image:
    with st.expander(
        "ดูภาพหน้าจอตอนเกิด Error",
        expanded=True,
    ):
        st.warning(
            "ภาพนี้อาจมีข้อมูลภายในองค์กร "
            "ไม่ควรส่งต่อให้บุคคลภายนอก"
        )

        st.image(
            st.session_state.debug_image,
            caption="หน้าจอ Browser ตอนเกิด Error",
            use_container_width=True,
        )


# ============================================================
# DOWNLOAD LOG
# ============================================================

if st.session_state.rpa_logs:
    log_timestamp = datetime.now(
        BANGKOK_TIMEZONE
    ).strftime("%Y%m%d_%H%M%S")

    st.download_button(
        label="ดาวน์โหลด Log",
        data="\n".join(
            st.session_state.rpa_logs
        ),
        file_name=(
            f"ams_rpa_log_{log_timestamp}.txt"
        ),
        mime="text/plain",
        use_container_width=True,
    )