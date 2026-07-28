"""
Auto-apply to LinkedIn Easy Apply and Indeed Apply jobs using Selenium.

WARNING: Automated job applications may violate platform Terms of Service.
LinkedIn in particular actively detects and blocks automation.
Recommended: Start with auto_apply=false in config.yaml and review
email notifications manually first. Enable auto-apply only for "Easy Apply"
jobs after you're confident the system is working correctly.
"""

import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Selenium imports — these will fail gracefully if not installed
try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.keys import Keys
    from selenium.common.exceptions import (
        TimeoutException, NoSuchElementException, WebDriverException
    )
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    logger.warning("undetected-chromedriver or selenium not installed — auto-apply disabled")


def _make_driver(headless: bool = False) -> "uc.Chrome":
    """Create an undetected Chrome driver."""
    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,900")
    return uc.Chrome(options=options)


def _wait_and_click(driver, wait, selector, by=By.CSS_SELECTOR, timeout=10):
    el = wait.until(EC.element_to_be_clickable((by, selector)))
    driver.execute_script("arguments[0].scrollIntoView(true);", el)
    time.sleep(0.5)
    el.click()
    return el


def _fill_field(driver, wait, selector, value, by=By.CSS_SELECTOR):
    el = wait.until(EC.presence_of_element_located((by, selector)))
    el.clear()
    el.send_keys(value)


class LinkedInApplier:
    def __init__(self, email: str, password: str, personal_info: dict):
        self.email = email
        self.password = password
        self.info = personal_info
        self.driver = None
        self.logged_in = False

    def _login(self):
        driver = self.driver
        wait = WebDriverWait(driver, 20)
        driver.get("https://www.linkedin.com/login")
        time.sleep(2)
        _fill_field(driver, wait, "#username", self.email)
        _fill_field(driver, wait, "#password", self.password)
        _wait_and_click(driver, wait, "[type='submit']")
        time.sleep(3)
        if "feed" in driver.current_url or "mynetwork" in driver.current_url:
            self.logged_in = True
            logger.info("LinkedIn: logged in successfully")
        else:
            raise Exception("LinkedIn login failed — check credentials or CAPTCHA")

    def _handle_easy_apply_form(self, resume_path: str) -> bool:
        """Fill multi-step Easy Apply form. Returns True on success."""
        driver = self.driver
        wait = WebDriverWait(driver, 15)
        info = self.info

        for step in range(10):  # Max 10 form steps
            time.sleep(1.5)

            # Upload resume if file input is visible
            try:
                file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                for fi in file_inputs:
                    if fi.is_displayed() or True:
                        fi.send_keys(os.path.abspath(resume_path))
                        time.sleep(2)
            except Exception:
                pass

            # Fill phone number if field exists
            for selector in ["input[id*='phone']", "input[name*='phone']"]:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, selector)
                    if el.is_displayed():
                        el.clear()
                        el.send_keys(info.get("phone", ""))
                except Exception:
                    pass

            # Fill city if field exists
            for selector in ["input[id*='city']", "input[name*='city']"]:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, selector)
                    if el.is_displayed() and not el.get_attribute("value"):
                        el.send_keys(info.get("city", "Dublin"))
                except Exception:
                    pass

            # Handle radio buttons / yes-no questions (work authorization, etc.)
            try:
                yes_options = driver.find_elements(
                    By.XPATH, "//label[contains(translate(.,'YES','yes'),'yes')]"
                )
                for opt in yes_options:
                    if opt.is_displayed():
                        opt.click()
                        time.sleep(0.3)
            except Exception:
                pass

            # Check for Review/Submit button
            for btn_text in ["Submit application", "Review", "Next", "Continue"]:
                try:
                    btn = driver.find_element(
                        By.XPATH, f"//button[contains(.,'{btn_text}')]"
                    )
                    if btn.is_displayed() and btn.is_enabled():
                        if btn_text == "Submit application":
                            btn.click()
                            time.sleep(2)
                            logger.info("LinkedIn Easy Apply: submitted successfully")
                            return True
                        else:
                            btn.click()
                            time.sleep(1.5)
                            break
                except NoSuchElementException:
                    pass

            # Check if modal closed (success)
            try:
                driver.find_element(By.CSS_SELECTOR, ".artdeco-modal__content")
            except NoSuchElementException:
                return True  # Modal closed — likely submitted

        return False

    def apply(self, job_url: str, resume_path: str, dry_run: bool = False) -> str:
        """Attempt Easy Apply on a LinkedIn job. Returns status string."""
        if not SELENIUM_AVAILABLE:
            return "skipped:no_selenium"

        try:
            if self.driver is None:
                self.driver = _make_driver(headless=False)

            if not self.logged_in:
                self._login()

            wait = WebDriverWait(self.driver, 20)
            self.driver.get(job_url)
            time.sleep(3)

            # Look for Easy Apply button
            try:
                easy_apply_btn = self.driver.find_element(
                    By.XPATH, "//button[contains(@class,'jobs-apply-button')]"
                )
                btn_text = easy_apply_btn.text.strip()
                if "Easy Apply" not in btn_text:
                    logger.info(f"LinkedIn: no Easy Apply button — skipping {job_url}")
                    return "skipped:no_easy_apply"
            except NoSuchElementException:
                return "skipped:no_easy_apply"

            if dry_run:
                logger.info(f"[DRY RUN] Would Easy Apply to: {job_url}")
                return "dry_run"

            easy_apply_btn.click()
            time.sleep(2)

            success = self._handle_easy_apply_form(resume_path)
            return "applied" if success else "failed:form_error"

        except Exception as e:
            logger.error(f"LinkedIn apply error: {e}")
            return f"failed:{str(e)[:50]}"

    def quit(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None


class IndeedApplier:
    def __init__(self, email: str, password: str, personal_info: dict):
        self.email = email
        self.password = password
        self.info = personal_info
        self.driver = None
        self.logged_in = False

    def _login(self):
        driver = self.driver
        wait = WebDriverWait(driver, 20)
        driver.get("https://ie.indeed.com/account/login")
        time.sleep(2)
        try:
            _fill_field(driver, wait, "#ifl-InputFormField-3", self.email)
            _wait_and_click(driver, wait, "#ifl-InputFormField-3 ~ button, [type='submit']")
            time.sleep(2)
            _fill_field(driver, wait, "input[type='password']", self.password)
            _wait_and_click(driver, wait, "[type='submit']")
            time.sleep(3)
            self.logged_in = True
            logger.info("Indeed: logged in successfully")
        except Exception as e:
            raise Exception(f"Indeed login failed: {e}")

    def apply(self, job_url: str, resume_path: str, dry_run: bool = False) -> str:
        """Attempt Indeed Apply. Returns status string."""
        if not SELENIUM_AVAILABLE:
            return "skipped:no_selenium"

        try:
            if self.driver is None:
                self.driver = _make_driver(headless=False)

            if not self.logged_in:
                self._login()

            wait = WebDriverWait(self.driver, 20)
            self.driver.get(job_url)
            time.sleep(3)

            # Check for Indeed Apply button (not "Apply on company site")
            try:
                apply_btn = self.driver.find_element(
                    By.XPATH,
                    "//button[contains(@class,'ia-continueButton') or "
                    "contains(.,'Apply now') and not(contains(.,'company site'))]"
                )
            except NoSuchElementException:
                return "skipped:no_indeed_apply"

            if dry_run:
                logger.info(f"[DRY RUN] Would Indeed Apply to: {job_url}")
                return "dry_run"

            apply_btn.click()
            time.sleep(2)

            # Handle multi-step Indeed application
            for step in range(8):
                time.sleep(2)

                # Upload resume
                try:
                    file_input = self.driver.find_element(By.CSS_SELECTOR, "input[type='file']")
                    file_input.send_keys(os.path.abspath(resume_path))
                    time.sleep(2)
                except Exception:
                    pass

                # Fill phone
                for sel in ["input[name*='phone']", "#phoneNumber", "input[id*='phone']"]:
                    try:
                        el = self.driver.find_element(By.CSS_SELECTOR, sel)
                        if el.is_displayed() and not el.get_attribute("value"):
                            el.send_keys(self.info.get("phone", ""))
                    except Exception:
                        pass

                # Continue/Submit
                for btn_text in ["Submit", "Continue", "Next"]:
                    try:
                        btn = self.driver.find_element(
                            By.XPATH, f"//button[contains(.,'{btn_text}')]"
                        )
                        if btn.is_displayed() and btn.is_enabled():
                            btn.click()
                            time.sleep(1.5)
                            if btn_text == "Submit":
                                return "applied"
                            break
                    except NoSuchElementException:
                        pass

                # Check for success message
                if any(word in self.driver.page_source for word in
                       ["application submitted", "successfully applied", "thank you for applying"]):
                    return "applied"

            return "failed:form_incomplete"

        except Exception as e:
            logger.error(f"Indeed apply error: {e}")
            return f"failed:{str(e)[:50]}"

    def quit(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None


def apply_to_jobs(
    jobs: list[dict],
    tailored_resumes: dict[str, str],
    config: dict,
    dry_run: bool = False,
) -> dict[str, str]:
    """
    Apply to all eligible jobs. Returns {job_id: status}.
    Only applies to LinkedIn Easy Apply and Indeed Apply jobs.
    Skips jobs requiring company-site application.
    """
    if not SELENIUM_AVAILABLE:
        logger.warning("Selenium not available — skipping auto-apply")
        return {job["id"]: "skipped:no_selenium" for job in jobs}

    statuses = {}
    linkedin_cfg = config.get("linkedin", {})
    indeed_cfg = config.get("indeed", {})
    personal = config.get("personal_info", {})
    default_resume = config["resume"]["path"]

    linkedin_applier = None
    indeed_applier = None

    try:
        for job in jobs:
            job_id = job["id"]
            platform = job["platform"]
            resume_path = tailored_resumes.get(job_id, default_resume)

            if platform == "linkedin" and linkedin_cfg.get("email"):
                if linkedin_applier is None:
                    linkedin_applier = LinkedInApplier(
                        linkedin_cfg["email"], linkedin_cfg["password"], personal
                    )
                status = linkedin_applier.apply(job["url"], resume_path, dry_run)
                statuses[job_id] = status
                logger.info(f"LinkedIn apply [{job['title']} @ {job['company']}]: {status}")
                time.sleep(5)  # Respectful delay between applications

            elif platform == "indeed" and indeed_cfg.get("email"):
                if indeed_applier is None:
                    indeed_applier = IndeedApplier(
                        indeed_cfg["email"], indeed_cfg["password"], personal
                    )
                status = indeed_applier.apply(job["url"], resume_path, dry_run)
                statuses[job_id] = status
                logger.info(f"Indeed apply [{job['title']} @ {job['company']}]: {status}")
                time.sleep(5)

            else:
                statuses[job_id] = "skipped:manual_apply_required"

    finally:
        if linkedin_applier:
            linkedin_applier.quit()
        if indeed_applier:
            indeed_applier.quit()

    return statuses
