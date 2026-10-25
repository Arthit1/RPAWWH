from datetime import datetime
from pathlib import Path

from playwright.sync_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


# ============================================================
# 1. ข้อมูลสำหรับ Debug
# ============================================================

LOGIN_URL = "https://ams.cpall.co.th/login.action"

USERNAME = ""
PASSWORD = ""

# รหัสสาขาที่ต้องการค้นหา
BRANCH_CODE = "10319"
DOWNLOAD_FOLDER = Path(r"D:\Code\WWHRPA")

DOWNLOAD_TIMEOUT = 120_000
SEARCH_TO_EXPORT_DELAY = 15_000

# ============================================================
# 2. ตั้งค่า Browser
# ============================================================

HEADLESS = False
SLOW_MO = 300

DEFAULT_TIMEOUT = 15_000
LOGIN_TIMEOUT = 30_000
LOADING_TIMEOUT = 60_000

# เปิด Browser ค้างไว้หลังค้นหา
KEEP_BROWSER_OPEN = True


# ============================================================
# 3. Selector หน้า Login
# แก้ Username และ Password ให้ตรงกับ Element จริง
# ============================================================

USERNAME_SELECTOR = "#username"
PASSWORD_SELECTOR = "#password"

LOGIN_BUTTON_SELECTOR = "button.button-login"

# ใช้ช่องรหัสสาขาเป็นตัวตรวจสอบว่า Login สำเร็จแล้ว
LOGIN_SUCCESS_SELECTOR = "#actionLocCode"

# หากพบ Element แจ้งเตือน Login ผิด ให้ใส่ Selector ที่นี่
LOGIN_ERROR_SELECTOR = ""

EXPORT_BUTTON_SELECTOR = (
    'input.button-login'
    '[type="button"]'
    '[value="Export to excel"]'
)


# ============================================================
# 4. Selector หน้าค้นหาเอกสาร
# ============================================================

# ช่องรหัสสาขา
BRANCH_CODE_SELECTOR = "#actionLocCode"

# รูปแว่นขยายสำหรับค้นหารหัสสาขา
BRANCH_SEARCH_BUTTON_SELECTOR = (
    'img.input-icon'
    '[onclick*="searchPopupCostCenter"]'
    '[onclick*="actionLocCode"]'
)

# Dropdown สถานะ
STATUS_SELECTOR = "#statusId"

# ค่า "ทั้งหมด" เป็นช่องว่าง 1 ตัว
STATUS_ALL_VALUE = " "

# Checkbox
APPROVAL_CHECKBOX_SELECTOR = "#isActive"

# ปุ่มค้นหา
SEARCH_BUTTON_SELECTOR = (
    'input.button-login[type="button"][value="ค้นหา"]'
)

# Popup ที่ต้องรอให้ซ่อน
LOADING_POPUP_SELECTOR = "#ui-datepicker-div"

# หากทราบ Selector ของตารางผลลัพธ์ภายหลัง ให้ใส่ตรงนี้
SEARCH_RESULT_SELECTOR = ""


# ============================================================
# 5. Folder สำหรับเก็บข้อมูล Debug
# ============================================================

DEBUG_FOLDER = Path("debug_output")
DEBUG_FOLDER.mkdir(exist_ok=True)


# ============================================================
# 6. ฟังก์ชันบันทึกข้อมูล Debug
# ============================================================

def save_debug_files(
    page: Page,
    file_prefix: str,
) -> None:

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    screenshot_path = (
        DEBUG_FOLDER /
        f"{file_prefix}_{timestamp}.png"
    )

    html_path = (
        DEBUG_FOLDER /
        f"{file_prefix}_{timestamp}.html"
    )

    page.screenshot(
        path=str(screenshot_path),
        full_page=True,
    )

    html_path.write_text(
        page.content(),
        encoding="utf-8",
    )

    print(f"Screenshot: {screenshot_path}")
    print(f"HTML: {html_path}")


# ============================================================
# 7. จัดการ JavaScript Alert
# ============================================================

def handle_dialog(dialog) -> None:
    """
    แสดงข้อความ Alert และกด OK อัตโนมัติ
    """

    print(f"พบข้อความแจ้งเตือน: {dialog.message}")
    dialog.accept()


# ============================================================
# 8. รอหน้าเว็บโหลด
# ============================================================

def wait_until_page_ready(page: Page) -> None:

    try:
        page.wait_for_load_state(
            "domcontentloaded",
            timeout=LOADING_TIMEOUT,
        )
    except PlaywrightTimeoutError:
        print("หน้าเว็บใช้เวลาโหลด DOM นานกว่าปกติ")

    try:
        page.wait_for_load_state(
            "networkidle",
            timeout=10_000,
        )
    except PlaywrightTimeoutError:
        # บางเว็บไซต์มีการเชื่อมต่อ Network ตลอดเวลา
        print("Network ยังมีการทำงานต่อเนื่อง")


# ============================================================
# 9. รอ Popup หาย
# ============================================================

def wait_for_loading_popup(page: Page) -> None:
    """
    รอจน Popup ไม่แสดงบนหน้าจอ
    """

    popup = page.locator(
        LOADING_POPUP_SELECTOR
    ).first

    if popup.count() == 0:
        print("ไม่พบ Loading Popup")
        return

    try:
        if popup.is_visible():
            print("กำลังรอ Popup หาย...")

            popup.wait_for(
                state="hidden",
                timeout=LOADING_TIMEOUT,
            )

            print("Popup หายแล้ว")
        else:
            print("Popup อยู่ในสถานะซ่อนแล้ว")

    except PlaywrightTimeoutError:
        save_debug_files(
            page,
            "popup_timeout",
        )

        raise RuntimeError(
            "Popup ไม่หายภายในเวลาที่กำหนด"
        )


# ============================================================
# 10. ตรวจสอบข้อความ Login Error
# ============================================================

def get_login_error(page: Page) -> str | None:

    if not LOGIN_ERROR_SELECTOR:
        return None

    error_element = page.locator(
        LOGIN_ERROR_SELECTOR
    ).first

    if error_element.count() == 0:
        return None

    try:
        if error_element.is_visible():
            return error_element.inner_text().strip()
    except Exception:
        return None

    return None


# ============================================================
# 11. Login เข้า AMS
# ============================================================

def login_ams(
    page: Page,
    username: str,
    password: str,
) -> None:

    print("\nกำลังเปิดหน้า Login...")

    page.goto(
        LOGIN_URL,
        wait_until="domcontentloaded",
        timeout=LOGIN_TIMEOUT,
    )

    username_element = page.locator(
        USERNAME_SELECTOR
    ).first

    password_element = page.locator(
        PASSWORD_SELECTOR
    ).first

    login_button = page.locator(
        LOGIN_BUTTON_SELECTOR
    ).first

    username_element.wait_for(
        state="visible",
        timeout=DEFAULT_TIMEOUT,
    )

    password_element.wait_for(
        state="visible",
        timeout=DEFAULT_TIMEOUT,
    )

    # --------------------------------------------------------
    # กรอก Username
    # --------------------------------------------------------

    print("กำลังกรอก Username...")

    username_element.click()
    username_element.press("Control+A")
    username_element.press("Backspace")

    username_element.type(
        username,
        delay=100,
    )

    username_element.press("Tab")

    # --------------------------------------------------------
    # กรอก Password
    # --------------------------------------------------------

    print("กำลังกรอก Password...")

    password_element.click()
    password_element.press("Control+A")
    password_element.press("Backspace")

    password_element.type(
        password,
        delay=100,
    )

    password_element.press("Tab")

    # --------------------------------------------------------
    # ตรวจสอบข้อมูลก่อนกด Login
    # --------------------------------------------------------

    username_value = username_element.input_value()
    password_value = password_element.input_value()

    print(f"Username ก่อน Login: {username_value}")
    print(
        "ความยาว Password ก่อน Login: "
        f"{len(password_value)} ตัวอักษร"
    )

    if not username_value:
        raise RuntimeError(
            "Username ไม่ถูกกรอกลงในหน้าเว็บไซต์"
        )

    if not password_value:
        raise RuntimeError(
            "Password ไม่ถูกกรอกลงในหน้าเว็บไซต์"
        )

    # --------------------------------------------------------
    # กด Login
    # --------------------------------------------------------

    print("กำลังกดปุ่ม Login...")

    login_button.wait_for(
        state="visible",
        timeout=DEFAULT_TIMEOUT,
    )

    login_button.click()

    wait_until_page_ready(page)

    # รอช่องรหัสสาขา ซึ่งใช้ยืนยันว่า Login สำเร็จ
    try:
        page.locator(
            LOGIN_SUCCESS_SELECTOR
        ).first.wait_for(
            state="visible",
            timeout=LOGIN_TIMEOUT,
        )

    except PlaywrightTimeoutError:
        login_error = get_login_error(page)

        save_debug_files(
            page,
            "login_failed",
        )

        if login_error:
            raise RuntimeError(
                f"Login ไม่สำเร็จ: {login_error}"
            )

        raise RuntimeError(
            "Login ไม่สำเร็จ หรือไม่พบช่องรหัสสาขา"
        )

    print("Login สำเร็จ")
    print(f"URL หลัง Login: {page.url}")

    # รอ Popup หลัง Login
    wait_for_loading_popup(page)


# ============================================================
# 12. กรอกรหัสสาขา
# ============================================================

def enter_branch_code(
    page: Page,
    branch_code: str,
) -> None:

    print(f"\nกำลังกรอกรหัสสาขา: {branch_code}")

    branch_input = page.locator(
        BRANCH_CODE_SELECTOR
    ).first

    branch_input.wait_for(
        state="visible",
        timeout=DEFAULT_TIMEOUT,
    )

    branch_input.click()
    branch_input.press("Control+A")
    branch_input.press("Backspace")

    branch_input.type(
        branch_code,
        delay=100,
    )

    # ทำให้ onkeyup และ change event ทำงาน
    branch_input.dispatch_event("keyup")
    branch_input.dispatch_event("change")
    branch_input.press("Tab")

    entered_value = branch_input.input_value()

    print(f"รหัสสาขาที่กรอกสำเร็จ: {entered_value}")

    if entered_value != branch_code:
        raise RuntimeError(
            "รหัสสาขาที่กรอกไม่ตรงกับค่าที่กำหนด"
        )


# ============================================================
# 13. กดปุ่มค้นหารหัสสาขา
# ============================================================

def click_branch_search_button(page: Page) -> None:

    print("กำลังกดปุ่มค้นหารหัสสาขา...")

    search_icon = page.locator(
        BRANCH_SEARCH_BUTTON_SELECTOR
    ).first

    search_icon.wait_for(
        state="visible",
        timeout=DEFAULT_TIMEOUT,
    )

    search_icon.click()

    # รอ JavaScript หรือ Popup ทำงาน
    page.wait_for_timeout(2_000)

    wait_for_loading_popup(page)

    print("กดปุ่มค้นหารหัสสาขาเรียบร้อย")


# ============================================================
# 14. เลือกสถานะทั้งหมด
# ============================================================

def select_all_status(page: Page) -> None:

    print("กำลังเลือกสถานะ: ทั้งหมด")

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

    selected_value = status_dropdown.input_value()

    print(
        f"ค่าของสถานะที่เลือก: {selected_value!r}"
    )

    if selected_value != STATUS_ALL_VALUE:
        raise RuntimeError(
            "ไม่สามารถเลือกสถานะทั้งหมดได้"
        )


# ============================================================
# 15. เลือก Checkbox
# ============================================================

def uncheck_approval_checkbox(page: Page) -> None:

    print("กำลังยกเลิกการเลือก Checkbox...")

    checkbox = page.locator(
        APPROVAL_CHECKBOX_SELECTOR
    ).first

    checkbox.wait_for(
        state="visible",
        timeout=DEFAULT_TIMEOUT,
    )

    # หาก Checkbox ถูกเลือกอยู่ ให้ยกเลิกการเลือก
    checkbox.uncheck()

    if checkbox.is_checked():
        raise RuntimeError(
            "ไม่สามารถยกเลิกการเลือก Checkbox ได้"
        )

    print("ยกเลิกการเลือก Checkbox เรียบร้อย")

# ============================================================
# 16. กดปุ่มค้นหา
# ============================================================

def click_search_button(page: Page) -> None:

    print("กำลังกดปุ่มค้นหา...")

    search_button = page.locator(
        SEARCH_BUTTON_SELECTOR
    ).first

    search_button.wait_for(
        state="visible",
        timeout=DEFAULT_TIMEOUT,
    )

    search_button.click()

    wait_until_page_ready(page)
    wait_for_loading_popup(page)

    # ถ้ามี Selector ตารางผลลัพธ์ ให้รอตารางแสดง
    if SEARCH_RESULT_SELECTOR:
        page.locator(
            SEARCH_RESULT_SELECTOR
        ).first.wait_for(
            state="visible",
            timeout=LOADING_TIMEOUT,
        )
    else:
        # รอ AJAX ของระบบชั่วคราว
        page.wait_for_timeout(3_000)

    save_debug_files(
        page,
        "after_search",
    )

    print("ค้นหาข้อมูลเรียบร้อย")


# ============================================================
# 17. ขั้นตอนค้นหาข้อมูล
# ============================================================

def search_documents(
    page: Page,
    branch_code: str,
) -> None:

    enter_branch_code(
        page,
        branch_code,
    )

    click_branch_search_button(page)

    select_all_status(page)

    uncheck_approval_checkbox(page)

    click_search_button(page)

    print(
        "\nค้นหาเรียบร้อย "
        f"กำลังรอข้อมูลโหลด {SEARCH_TO_EXPORT_DELAY / 1000:.0f} วินาที..."
    )

    page.wait_for_timeout(
        SEARCH_TO_EXPORT_DELAY
    )

    # รอ Popup หายอีกครั้งก่อน Export
    wait_for_loading_popup(page)

    print("ครบเวลารอแล้ว กำลังเริ่ม Export...")

    # 3. กด Export
    downloaded_file = export_excel(page)

    return downloaded_file
# ============================================================
# 18.export_excel
# ============================================================
def export_excel(page: Page) -> Path:

    print("\nกำลัง Export ข้อมูลเป็น Excel...")

    # สร้าง Folder หากยังไม่มี
    DOWNLOAD_FOLDER.mkdir(
        parents=True,
        exist_ok=True,
    )

    export_button = page.locator(
        EXPORT_BUTTON_SELECTOR
    ).first

    export_button.wait_for(
        state="visible",
        timeout=DEFAULT_TIMEOUT,
    )

    wait_for_loading_popup(page)

    # ดักจับ Download หลังจากกดปุ่ม Export
    with page.expect_download(
        timeout=DOWNLOAD_TIMEOUT
    ) as download_info:

        export_button.click()

    download = download_info.value

    original_filename = Path(
        download.suggested_filename
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    # ถ้าเว็บไซต์ไม่ได้ส่งนามสกุลไฟล์มา ให้ใช้ .xlsx
    file_extension = (
        original_filename.suffix or ".xlsx"
    )

    new_filename = (
        f"{original_filename.stem}_"
        f"{timestamp}"
        f"{file_extension}"
    )

    save_path = (
        DOWNLOAD_FOLDER / new_filename
    )

    download.save_as(
        str(save_path)
    )

    if not save_path.exists():
        raise RuntimeError(
            "ไม่พบไฟล์หลังจาก Download"
        )

    print("Export สำเร็จ")
    print(f"บันทึกไฟล์ที่: {save_path}")

    return save_path
# ============================================================
# เริ่มต้นระบบ
# ============================================================

def main() -> None:

    if (
        not USERNAME.strip()
        or USERNAME == "ใส่_username_ตรงนี้"
    ):
        raise ValueError(
            "กรุณากำหนด USERNAME"
        )

    if (
        not PASSWORD
        or PASSWORD == "ใส่_password_ตรงนี้"
    ):
        raise ValueError(
            "กรุณากำหนด PASSWORD"
        )

    if (
        not BRANCH_CODE.strip()
        or BRANCH_CODE == "ใส่รหัสสาขาตรงนี้"
    ):
        raise ValueError(
            "กรุณากำหนด BRANCH_CODE"
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=HEADLESS,
            slow_mo=SLOW_MO,
        )

        context = browser.new_context(
            viewport={
                "width": 1440,
                "height": 900,
            },
            ignore_https_errors=True,
        )

        page = context.new_page()

        page.set_default_timeout(
            DEFAULT_TIMEOUT
        )

        # รับ JavaScript Alert
        page.on(
            "dialog",
            handle_dialog,
        )

        try:
            # Login
            login_ams(
                page=page,
                username=USERNAME,
                password=PASSWORD,
            )

            # กรอกเงื่อนไขและค้นหา
            search_documents(
                page=page,
                branch_code=BRANCH_CODE,
            )

            if KEEP_BROWSER_OPEN:
                input(
                    "\nดำเนินการเสร็จแล้ว "
                    "กด Enter เพื่อปิด Browser..."
                )

        except PlaywrightTimeoutError as error:
            print("\nไม่พบ Element ภายในเวลาที่กำหนด")
            print(f"รายละเอียด: {error}")

            save_debug_files(
                page,
                "timeout_error",
            )

            input(
                "\nกด Enter เพื่อปิด Browser..."
            )

        except Exception as error:
            print("\nเกิดข้อผิดพลาดระหว่างทำงาน")
            print(f"รายละเอียด: {error}")

            save_debug_files(
                page,
                "rpa_error",
            )

            input(
                "\nกด Enter เพื่อปิด Browser..."
            )

        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()