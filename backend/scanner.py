import ipaddress
import json
import logging
import socket
from urllib.parse import urlsplit
from typing import Any


logger = logging.getLogger(__name__)

SAFE_SCHEMES = {"http", "https"}
MAX_ELEMENTS_PER_CATEGORY = 100


def _is_allowed_ip(ip_value: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Allow only globally routable public IPs and reject local/private/reserved ranges."""
    return (
        not ip_value.is_private
        and not ip_value.is_loopback
        and not ip_value.is_link_local
        and not ip_value.is_multicast
        and not ip_value.is_reserved
        and not ip_value.is_unspecified
        and ip_value.is_global
    )


def _resolve_hostname(hostname: str) -> list[str]:
    try:
        address_info = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Unable to resolve host '{hostname}'") from exc

    resolved: list[str] = []
    for _, _, _, _, sockaddr in address_info:
        ip_str = sockaddr[0]
        if ip_str not in resolved:
            resolved.append(ip_str)

    if not resolved:
        raise ValueError(f"Host '{hostname}' resolved to no valid addresses")

    return resolved


def validate_destination_url(raw_url: str) -> str:
    """Validate legal HTTP/HTTPS destinations and reject private/local/reserved addresses.

    This is a defense-in-depth check, not a perfect SSRF blocker against every DNS rebinding
    or resolver manipulation scenario; we also validate each request and redirect destination.
    """
    # DNS rebinding is still possible in some edge cases: the host may resolve differently
    # at request time than at initial validation time, so every request/redirect is checked too.
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise ValueError("A valid URL is required")

    parsed = urlsplit(raw_url)
    if parsed.scheme.lower() not in SAFE_SCHEMES:
        raise ValueError("Only HTTP and HTTPS URLs are allowed")

    hostname = parsed.hostname
    if hostname is None or not hostname.strip():
        raise ValueError("URL hostname is missing")

    host = hostname.strip().lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        raise ValueError("Localhost destinations are not allowed")

    try:
        ip_value = ipaddress.ip_address(host)
    except ValueError:
        addresses = _resolve_hostname(host)
        for address in addresses:
            try:
                candidate = ipaddress.ip_address(address)
            except ValueError:
                continue
            if not _is_allowed_ip(candidate):
                raise ValueError(f"Host '{host}' resolves to an unsafe address ({candidate})")
        return raw_url

    if not _is_allowed_ip(ip_value):
        raise ValueError(f"Destination '{host}' is not allowed")

    return raw_url


def _is_visible(element: Any) -> bool:
    if element is None:
        return False
    return bool(
        element
        and element.get("display") != "none"
        and element.get("visibility") != "hidden"
        and (element.get("width") or element.get("height") or element.get("text"))
    )


async def _collect_headings(page: Any) -> list[str]:
    result = await page.evaluate(
        """
        () => {
          const nodes = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6'));
          return nodes
            .filter((node) => {
              if (!(node instanceof HTMLElement)) return false;
              const style = window.getComputedStyle(node);
              if (style.display === 'none' || style.visibility === 'hidden') return false;
              const rect = node.getBoundingClientRect();
              return rect.width > 0 || rect.height > 0 || node.innerText.trim().length > 0;
            })
            .slice(0, 100)
            .map((node) => node.innerText.trim())
            .filter((text) => text.length > 0);
        }
        """
    )
    return [str(item) for item in result][:MAX_ELEMENTS_PER_CATEGORY]


async def _collect_buttons(page: Any) -> list[dict[str, str]]:
    result = await page.evaluate(
        """
        () => {
          const selector = 'button, input[type="button"], input[type="submit"], input[type="reset"], [role="button"]';
          const nodes = Array.from(document.querySelectorAll(selector));
          const visible = nodes.filter((node) => {
            if (!(node instanceof HTMLElement)) return false;
            const style = window.getComputedStyle(node);
            if (style.display === 'none' || style.visibility === 'hidden') return false;
            const text = node.innerText.trim() || node.getAttribute('value') || node.getAttribute('aria-label') || node.getAttribute('title') || '';
            if (!text && node instanceof HTMLInputElement && node.type !== 'submit') return false;
            const rect = node.getBoundingClientRect();
            return rect.width > 0 || rect.height > 0 || text.length > 0;
          });
          return visible.slice(0, 100).map((node) => ({
            text: (node.innerText || node.getAttribute('value') || node.getAttribute('aria-label') || node.getAttribute('title') || '').trim(),
            type: node.tagName.toLowerCase(),
            form_id: node.getAttribute('form') || null,
          }));
        }
        """
    )
    return [
        {
            "text": str(item.get("text") or ""),
            "type": str(item.get("type") or ""),
            "form_id": item.get("form_id"),
        }
        for item in result
    ][:MAX_ELEMENTS_PER_CATEGORY]


async def _collect_links(page: Any) -> list[dict[str, str]]:
    result = await page.evaluate(
        """
        () => {
          const nodes = Array.from(document.querySelectorAll('a[href]'));
          const visible = nodes.filter((node) => {
            if (!(node instanceof HTMLElement)) return false;
            const style = window.getComputedStyle(node);
            if (style.display === 'none' || style.visibility === 'hidden') return false;
            const rect = node.getBoundingClientRect();
            return rect.width > 0 || rect.height > 0 || node.innerText.trim().length > 0;
          });
          return visible.slice(0, 100).map((node) => ({
            text: (node.innerText || '').trim(),
            href: node.getAttribute('href') || '',
          }));
        }
        """
    )
    return [
        {
            "text": str(item.get("text") or ""),
            "href": str(item.get("href") or ""),
        }
        for item in result
    ][:MAX_ELEMENTS_PER_CATEGORY]


async def _collect_inputs(page: Any) -> list[dict[str, Any]]:
    result = await page.evaluate(
        """
        () => {
          const selector = 'input, textarea, select';
          const nodes = Array.from(document.querySelectorAll(selector));
          const visible = nodes.filter((node) => {
            if (!(node instanceof HTMLElement)) return false;
            const style = window.getComputedStyle(node);
            if (style.display === 'none' || style.visibility === 'hidden') return false;
            const rect = node.getBoundingClientRect();
            return rect.width > 0 || rect.height > 0;
          });
          return visible.slice(0, 100).map((node) => ({
            type: node instanceof HTMLInputElement ? node.type : node.tagName.toLowerCase(),
            name: node.getAttribute('name') || null,
            placeholder: node.getAttribute('placeholder') || null,
            id: node.getAttribute('id') || null,
            required: node.hasAttribute('required'),
          }));
        }
        """
    )
    return [
        {
            "type": item.get("type"),
            "name": item.get("name"),
            "placeholder": item.get("placeholder"),
            "id": item.get("id"),
            "required": bool(item.get("required")),
        }
        for item in result
    ][:MAX_ELEMENTS_PER_CATEGORY]


async def _collect_forms(page: Any) -> list[dict[str, Any]]:
    result = await page.evaluate(
        """
        () => {
          const forms = Array.from(document.querySelectorAll('form'));
          const visibleForms = forms.filter((form) => {
            const style = window.getComputedStyle(form);
            if (style.display === 'none' || style.visibility === 'hidden') return false;
            const rect = form.getBoundingClientRect();
            return rect.width > 0 || rect.height > 0;
          });
          return visibleForms.slice(0, 50).map((form) => {
            const fields = Array.from(form.querySelectorAll('input, textarea, select')).slice(0, 50).map((node) => ({
              type: node instanceof HTMLInputElement ? node.type : node.tagName.toLowerCase(),
              name: node.getAttribute('name') || null,
              placeholder: node.getAttribute('placeholder') || null,
              id: node.getAttribute('id') || null,
              required: node.hasAttribute('required'),
            }));
            return {
              id: form.getAttribute('id') || null,
              action: form.getAttribute('action') || '',
              method: (form.getAttribute('method') || 'get').toLowerCase(),
              fields,
            };
          });
        }
        """
    )
    return [
        {
            "id": item.get("id"),
            "action": item.get("action"),
            "method": item.get("method"),
            "fields": list(item.get("fields") or []),
        }
        for item in result
    ][:MAX_ELEMENTS_PER_CATEGORY]


async def _collect_element_metadata(page: Any) -> dict[str, list[dict[str, Any]]]:
    metadata = await page.evaluate(
    """
                () => {
                    const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                    const textOf = (element) => {
                        if (element.matches('input, textarea, select, form')) return '';
                        return normalize(element.innerText || element.textContent || '');
                    };
                    const labelsOf = (element) => Array.from(element.labels || [])
                        .map((label) => textOf(label))
                        .filter(Boolean);
                    const associatedLabel = (element) => normalize(labelsOf(element).join(' '));
                    const accessibleName = (element) => {
                        const labelledBy = normalize(element.getAttribute('aria-labelledby'));
                        if (labelledBy) {
                            const referencedText = labelledBy.split(/\\s+/)
                                .map((id) => document.getElementById(id))
                                .filter(Boolean)
                                .map(textOf)
                                .filter(Boolean)
                                .join(' ');
                            if (referencedText) return normalize(referencedText);
                        }
                        const ariaLabel = normalize(element.getAttribute('aria-label'));
                        if (ariaLabel) return ariaLabel;
                        const label = associatedLabel(element);
                        if (label) return label;
                        const role = element.getAttribute('role');
                        const tag = element.tagName.toLowerCase();
                        if ((role || tag === 'button' || tag === 'a' || /^h[1-6]$/.test(tag)) && tag !== 'form') {
                            const text = textOf(element);
                            if (text) return text;
                            const alternativeText = Array.from(element.querySelectorAll('img[alt], svg title'))
                                .map((node) => normalize(node.getAttribute('alt') || node.textContent))
                                .filter(Boolean)
                                .join(' ');
                            if (alternativeText) return normalize(alternativeText);
                        }
                        if (element instanceof HTMLInputElement && ['button', 'submit', 'reset', 'image'].includes(element.type)) {
                            const value = normalize(element.getAttribute('value'));
                            const alternativeText = normalize(element.getAttribute('alt'));
                            if (alternativeText) return alternativeText;
                            if (value) return value;
                        }
                        return normalize(element.getAttribute('title'));
                    };
                    const roleOf = (element) => {
                        const explicitRole = normalize(element.getAttribute('role')).split(/\\s+/)[0];
                        if (explicitRole) return explicitRole;
                        const tag = element.tagName.toLowerCase();
                        if (/^h[1-6]$/.test(tag)) return 'heading';
                        if (tag === 'button' || element.matches('input[type="button"], input[type="submit"], input[type="reset"], input[type="image"]')) return 'button';
                        if (tag === 'a' && element.hasAttribute('href')) return 'link';
                        if (tag === 'textarea') return 'textbox';
                        if (tag === 'select') return element.multiple ? 'listbox' : 'combobox';
                        if (tag === 'input') {
                            const type = element.type;
                            if (type === 'hidden') return null;
                            if (type === 'checkbox' || type === 'radio' || type === 'range' || type === 'number') {
                                return { checkbox: 'checkbox', radio: 'radio', range: 'slider', number: 'spinbutton' }[type];
                            }
                            if (type === 'search') return 'searchbox';
                            if (['button', 'submit', 'reset', 'image'].includes(type)) return 'button';
                            if (['text', 'email', 'tel', 'url', 'password'].includes(type)) return 'textbox';
                            return null;
                        }
                        if (tag === 'form' && accessibleName(element)) return 'form';
                        return null;
                    };
                    const visible = (element) => {
                        const style = window.getComputedStyle(element);
                        const rects = Array.from(element.getClientRects());
                        return !element.hidden
                            && style.display !== 'none'
                            && style.visibility !== 'hidden'
                            && style.visibility !== 'collapse'
                            && rects.some((rect) => rect.width > 0 || rect.height > 0);
                    };
                    const cssEscape = (value) => CSS.escape(String(value));
                    const selectorCounts = new Map();
                    const countSelector = (selector) => {
                        if (!selectorCounts.has(selector)) {
                            try {
                                selectorCounts.set(selector, document.querySelectorAll(selector).length);
                            } catch {
                                selectorCounts.set(selector, null);
                            }
                        }
                        return selectorCounts.get(selector);
                    };
                    const addCandidate = (candidates, strategy, value, count) => {
                        if (value === null || value === undefined || value === '') return;
                        candidates.push({
                            strategy,
                            value,
                            match_count: count,
                            is_unique: count === 1,
                        });
                    };
                    const getMetadata = (element) => {
                        const tagName = element.tagName.toLowerCase();
                        const elementId = element.getAttribute('id') || null;
                        const name = element.getAttribute('name') || null;
                        const placeholder = element.getAttribute('placeholder') || null;
                        const testId = element.getAttribute('data-testid') || null;
                        const label = associatedLabel(element) || null;
                        const nameText = accessibleName(element);
                        const role = roleOf(element);
                        const disabled = element.matches(':disabled') || element.getAttribute('aria-disabled') === 'true';
                        const candidates = [];

                        if (testId) {
                            addCandidate(candidates, 'data-testid', testId, countSelector(`[data-testid=${cssEscape(testId)}]`));
                        }
                        if (role && nameText) {
                            const key = JSON.stringify([role, nameText]);
                              addCandidate(candidates, 'role', { role, name: nameText }, null);
                        }
                        if (label) {
                              addCandidate(candidates, 'label', label, null);
                        }
                        if (elementId) {
                            addCandidate(candidates, 'id', elementId, countSelector(`[id=${cssEscape(elementId)}]`));
                        }
                        if (name) {
                            addCandidate(candidates, 'name', name, countSelector(`[name=${cssEscape(name)}]`));
                        }
                        if (placeholder) {
                            addCandidate(candidates, 'placeholder', placeholder, countSelector(`[placeholder=${cssEscape(placeholder)}]`));
                        }

                        const cssValue = testId
                            ? `${tagName}[data-testid=${cssEscape(testId)}]`
                            : elementId
                                ? `${tagName}[id=${cssEscape(elementId)}]`
                                : name
                                    ? `${tagName}[name=${cssEscape(name)}]`
                                    : placeholder
                                        ? `${tagName}[placeholder=${cssEscape(placeholder)}]`
                                        : null;
                        if (cssValue) addCandidate(candidates, 'css', cssValue, countSelector(cssValue));

                        return {
                            tag_name: tagName,
                            element_id: elementId,
                            element_text: textOf(element),
                            accessible_name: nameText || null,
                            aria_role: role,
                            data_testid: testId,
                            visibility: visible(element) ? 'visible' : 'hidden',
                            enabled: !disabled,
                            disabled,
                            locator_candidates: candidates,
                        };
                    };
                    const inputMetadata = (element) => ({
                        ...getMetadata(element),
                        id: element.getAttribute('id') || null,
                        name: element.getAttribute('name') || null,
                        type: element instanceof HTMLInputElement ? element.type : element.tagName.toLowerCase(),
                        placeholder: element.getAttribute('placeholder') || null,
                        associated_label: associatedLabel(element) || null,
                        required: element.hasAttribute('required'),
                        readonly: Boolean(element.readOnly),
                        minlength: element.getAttribute('minlength'),
                        maxlength: element.getAttribute('maxlength'),
                        min: element.getAttribute('min'),
                        max: element.getAttribute('max'),
                        pattern: element.getAttribute('pattern'),
                    });
                    const buttonMetadata = (element) => ({
                        ...getMetadata(element),
                        text: textOf(element) || normalize(element.getAttribute('value')) || normalize(element.getAttribute('aria-label')) || normalize(element.getAttribute('title')),
                        type: element instanceof HTMLInputElement
                            ? element.type
                            : element instanceof HTMLButtonElement
                                ? element.type
                                : element.getAttribute('type'),
                        form_id: element.form ? (element.form.id || element.getAttribute('form') || null) : null,
                    });
                    const collect = (selector, mapper, limit = 100) =>
                        Array.from(document.querySelectorAll(selector)).slice(0, limit).map(mapper);

                    return {
                        headings: collect('h1, h2, h3, h4, h5, h6', getMetadata),
                        buttons: collect('button, input[type="button"], input[type="submit"], input[type="reset"], input[type="image"], [role="button"]', buttonMetadata),
                        links: collect('a[href]', (element) => ({
                            ...getMetadata(element),
                            text: textOf(element),
                            href: element.getAttribute('href') || '',
                            target: element.getAttribute('target'),
                            rel: element.getAttribute('rel'),
                        })),
                        inputs: collect('input, textarea, select', inputMetadata),
                        forms: collect('form', (form) => ({
                            ...getMetadata(form),
                            id: form.getAttribute('id') || null,
                            name: form.getAttribute('name') || null,
                            method: (form.getAttribute('method') || 'get').toLowerCase(),
                            action: form.getAttribute('action') || '',
                            fields: Array.from(document.querySelectorAll('input, textarea, select'))
                                .filter((field) => field.form === form)
                                .slice(0, 50)
                                .map(inputMetadata),
                            submit_buttons: Array.from(document.querySelectorAll('button, input[type="submit"], input[type="image"]'))
                                .filter((button) => button.form === form)
                                .slice(0, 50)
                                .map(buttonMetadata),
                        }), 50),
                    };
                }
        """
    )

    measured_counts: dict[str, int | None] = {}

    async def count_candidate(strategy: str, value: Any) -> int | None:
        key = json.dumps([strategy, value], ensure_ascii=False, sort_keys=True)
        if key in measured_counts:
            return measured_counts[key]

        try:
            if strategy == "data-testid":
                locator = page.get_by_test_id(value)
            elif strategy == "role":
                locator = page.get_by_role(
                    value["role"],
                    name=value["name"],
                    exact=True,
                    include_hidden=True,
                )
            elif strategy == "label":
                locator = page.get_by_label(value, exact=True)
            elif strategy == "placeholder":
                locator = page.get_by_placeholder(value, exact=True)
            elif strategy == "css":
                locator = page.locator(value)
            else:
                return None
            measured_counts[key] = await locator.count()
        except Exception:
            logger.debug("Unable to measure %s locator candidate", strategy, exc_info=True)
            measured_counts[key] = None

        return measured_counts[key]

    async def measure_element(element: dict[str, Any]) -> None:
        for candidate in element.get("locator_candidates", []):
            strategy = candidate.get("strategy")
            if strategy in {"data-testid", "role", "label", "placeholder", "css"}:
                count = await count_candidate(strategy, candidate.get("value"))
                candidate["match_count"] = count
                candidate["is_unique"] = count == 1

    for category in ("headings", "buttons", "links", "inputs", "forms"):
        for element in metadata.get(category, []):
            await measure_element(element)
            for field in element.get("fields", []):
                await measure_element(field)
            for button in element.get("submit_buttons", []):
                await measure_element(button)

    return metadata


async def _safe_close_resource(resource: Any, resource_name: str) -> None:
    if resource is None:
        return

    try:
        is_closed = getattr(resource, "is_closed", None)
        if callable(is_closed) and is_closed():
            return

        is_connected = getattr(resource, "is_connected", None)
        if callable(is_connected) and not is_connected():
            return
    except Exception:
        pass

    try:
        await resource.close()
    except Exception:
        logger.exception("Cleanup failed while closing %s", resource_name)


async def scan_application_url(target_url: str) -> dict[str, Any]:
    """Safely load a target page, collect visible DOM metadata, and return JSON-serializable data."""
    try:
        from playwright.async_api import async_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError("Playwright is not installed. Install backend requirements before scanning.") from exc

    validated_url = validate_destination_url(target_url)
    browser = None
    context = None
    page = None
    console_errors: list[str] = []
    page_errors: list[str] = []
    navigation_failures: list[str] = []

    async def guard_requests(route: Any, request: Any) -> None:
        try:
            validate_destination_url(request.url)
        except ValueError as exc:
            navigation_failures.append(f"Blocked unsafe destination: {request.url} ({exc})")
            await route.abort()
            return
        await route.continue_()

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            try:
                await context.route("**/*", guard_requests)
                page.on("console", lambda message: console_errors.append(f"{message.type}: {message.text}") if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.on("requestfailed", lambda request: navigation_failures.append(f"{request.url}: {request.failure or 'request failed'}"))

                try:
                    await page.goto(validated_url, wait_until="domcontentloaded", timeout=30_000)
                except Exception as exc:  # pragma: no cover - runtime browser navigation result
                    navigation_failures.append(f"Navigation failed: {exc}")
                    raise RuntimeError(f"Navigation failed: {exc}") from exc

                result = {
                    "page_title": await page.title(),
                    "final_url": page.url,
                    "headings": await _collect_headings(page),
                    "buttons": await _collect_buttons(page),
                    "links": await _collect_links(page),
                    "inputs": await _collect_inputs(page),
                    "forms": await _collect_forms(page),
                    "element_metadata": await _collect_element_metadata(page),
                    "console_errors": console_errors,
                    "page_errors": page_errors,
                    "navigation_failures": navigation_failures,
                }
                return result
            finally:
                # Close the context before the browser so page resources are cleaned up by the owner.
                # Cleanup is best-effort and logs errors without overwriting a valid scan result.
                await _safe_close_resource(context, "context")
                await _safe_close_resource(browser, "browser")
    except Exception:
        raise
