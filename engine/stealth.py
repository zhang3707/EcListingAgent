"""反检测脚本注入：在每个页面上下文初始化前抹除自动化特征。"""
from __future__ import annotations

STEALTH_JS = r"""
// 1. navigator.webdriver -> undefined
try { Object.defineProperty(navigator, 'webdriver', {get: () => undefined}); } catch (e) {}

// 2. 移除 cdp_* 等自动化全局变量
['cdc_adoQpoasnfa76pfcZLmcfl_Array',
 'cdc_adoQpoasnfa76pfcZLmcfl_Promise',
 'cdc_adoQpoasnfa76pfcZLmcfl_Symbol'].forEach(function (k) {
    if (k in window) { delete window[k]; }
});

// 3. plugins / mimeTypes 对齐真实 Chrome
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const make = (name, filename, desc) => ({
            name: name, filename: filename, description: desc, length: 1,
            0: {type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: ''}
        });
        return [make('PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
                make('Chrome PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
                make('Chromium PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format')];
    }
});

// 4. languages / vendor 对齐
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
Object.defineProperty(navigator, 'vendor', {get: () => 'Google Inc.'});

// 5. permissions API 修正
const origQuery = navigator.permissions && navigator.permissions.query;
if (origQuery) {
    navigator.permissions.query = (params) =>
        params.name === 'notifications'
            ? Promise.resolve({state: Notification.permission})
            : origQuery(params);
}

// 6. WebGL 厂商/渲染器指纹对齐
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function (p) {
    if (p === 37445) return 'Intel Inc.';                  // UNMASKED_VENDOR_WEBGL
    if (p === 37446) return 'Intel Iris OpenGL Engine';    // UNMASKED_RENDERER_WEBGL
    return getParameter.call(this, p);
};
"""

LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--no-default-browser-check",
    "--disable-dev-shm-usage",
    # 不传 --enable-automation
]


async def apply_stealth(context):
    """对浏览器上下文注入反检测脚本（每个文档加载前生效）。"""
    await context.add_init_script(STEALTH_JS)
