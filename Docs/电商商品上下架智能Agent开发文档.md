# 电商商品上下架智能 Agent 开发文档

> 本文档为开发落地蓝图，所有代码骨架均为可直接参考的 Python 实现示例，命名与目录与工程结构严格对齐，供编码阶段直接驱动。

## 一、项目概述

### 1.1 项目目标

搭建一套可自主完成电商商品上下架全流程的 Agent 工作流，覆盖 **ERP 素材库检索 → SKU / 价格匹配 → 多店铺上架 → 飞书多维表格数据归档** 完整链路。全程不依赖平台官方 API、不使用传统 RPA 工具，通过浏览器深度定制 + Agent 决策驱动实现拟人化、可风控对抗的店铺运营自动化。

### 1.2 核心约束边界

1. **禁止使用电商平台官方接口**：所有上下架操作通过前端页面交互完成，不调用商家开放 API、商品管理 API。
2. **禁止使用传统 RPA 工具**：不采用 UiPath、影刀、八爪鱼等商用 RPA，不基于图像识别 + 坐标点击路线，采用浏览器深度定制 + Agent 决策驱动的拟人化交互。
3. **兼容反自动化场景**：应对滑块验证码、登录态踢下线、短信验证码等平台风控。
4. **数据闭环**：所有上架流程数据自动同步至飞书多维表格，全链路可追溯。

### 1.3 业务总流程

```text
任务发起 → ERP素材库检索商品 → 多SKU价格匹配 → 目标店铺环境启动 → 登录态校验
    → 商品信息填充提交 → 上架结果校验 → 飞书多维表格归档 → 任务结束
    ↗ 异常分支：验证码处理、登录重试、失败重试、人工介入
```

## 二、整体技术架构

### 2.1 架构分层设计

五层解耦架构，兼顾稳定性、扩展性与反检测能力：

| 层级 | 核心职责 | 技术实现 |
| --- | --- | --- |
| 编排层 | 工作流编排、状态管理、异常分支决策 | LangGraph 状态机式 Agent 编排 |
| Skill 层 | 原子业务能力封装，可复用、可独立调试 | 标准化 Skill 模块（输入/输出/错误码规范） |
| 引擎层 | 浏览器交互、反检测、验证码处理 | 定制化 Playwright + 反检测增强引擎 |
| 数据层 | 素材存储、任务状态、店铺配置管理 | PostgreSQL + MinIO 对象存储 + 飞书多维表格 |
| 接口层 | 任务触发、店铺管理、状态查询 | FastAPI REST 接口 |
| 监控层 | 运行状态监控、异常告警、风控预警 | 结构化日志 + 飞书机器人告警 |

### 2.2 核心技术选型

- **Agent 编排**：LangGraph（支持复杂状态流转、异常分支、重试，适配多店铺多分支场景，内置 `interrupt` 机制支持人机协同挂起）
- **交互引擎**：Playwright 1.45+ 深度定制 + undetected-playwright 增强
- **反检测体系**：自研指纹隔离引擎 + 拟人化行为模拟 + CV 验证码识别（YOLOv8）
- **开发语言**：Python 3.11+
- **数据存储**：PostgreSQL（任务与配置）、MinIO（商品素材）
- **飞书对接**：飞书开放平台多维表格 Open API + 机器人告警
- **接口服务**：FastAPI + Uvicorn
- **部署方式**：Docker 容器化，单店铺单环境隔离

### 2.3 项目目录结构

工程化骨架，编码阶段严格遵循：

```text
EcListingAgent/
├── agent/                          # 编排层（LangGraph）
│   ├── __init__.py
│   ├── state.py                    # TaskState 全局状态定义
│   ├── graph.py                    # 工作流图构建与编译
│   ├── nodes.py                    # 工作流节点函数
│   ├── routes.py                   # 条件路由（边决策）
│   └── runner.py                   # 图执行入口 + checkpoint 恢复
│
├── skills/                         # Skill 层
│   ├── __init__.py
│   ├── base.py                     # BaseSkill 基类 + SkillResult + SkillStatus
│   ├── erp_material.py             # 5.2.1 ERP 素材检索
│   ├── sku_price.py                # 5.2.2 SKU 价格匹配
│   ├── listing.py                  # 5.2.3 店铺上架
│   ├── captcha.py                  # 5.2.4 验证码处理
│   ├── feishu_sync.py              # 5.2.5 飞书多维表格同步
│   └── env_manager.py              # 5.2.6 环境管理
│
├── engine/                         # 引擎层
│   ├── __init__.py
│   ├── browser.py                  # 浏览器环境封装（启动/上下文/持久化）
│   ├── stealth.py                  # 反检测脚本注入
│   ├── fingerprint.py              # 指纹生成与持久化
│   ├── humanize.py                 # 拟人化行为（鼠标/键盘/等待）
│   └── captcha/
│       ├── __init__.py
│       ├── slider_detect.py        # YOLOv8 缺口检测
│       ├── slider_track.py         # 贝塞尔轨迹生成
│       └── slider.py               # 滑块验证码编排
│
├── data/                           # 数据层
│   ├── __init__.py
│   ├── db.py                       # SQLAlchemy 引擎/会话
│   ├── models.py                   # ORM 模型（Task/Shop/ShopFingerprint/RunLog）
│   ├── minio_client.py             # MinIO 封装
│   └── repositories/
│       ├── __init__.py
│       ├── task_repo.py
│       └── shop_repo.py
│
├── integrations/                   # 外部系统对接
│   ├── __init__.py
│   ├── feishu/
│   │   ├── __init__.py
│   │   ├── client.py               # 飞书 API 客户端 + Token 管理
│   │   ├── bitable.py              # 多维表格读写
│   │   └── bot.py                  # 机器人告警通知
│   └── erp/
│       ├── __init__.py
│       └── erp_client.py           # ERP 数据库直连 / 网页端检索
│
├── api/                            # 接口层
│   ├── __init__.py
│   ├── server.py                   # FastAPI app 装配
│   └── routes/
│       ├── __init__.py
│       ├── tasks.py                # 任务触发与查询
│       └── shops.py                # 店铺配置管理
│
├── config/                         # 配置
│   ├── settings.py                 # 全局配置（pydantic-settings）
│   ├── shops/                      # 每店铺一个 YAML
│   │   └── shop_example.yaml
│   └── feishu.yaml                 # 飞书应用与表格配置
│
├── scripts/                        # 运维脚本
│   ├── init_db.py                  # 建表 + 初始化
│   ├── train_slider.py             # 滑块缺口检测模型训练
│   └── login_patrol.py             # 登录态每日巡检
│
├── tests/                          # 测试
│   ├── test_skills/
│   ├── test_engine/
│   └── test_graph/
│
├── data_persist/                   # 运行时持久化（gitignore）
│   ├── browser_profiles/           # 每店铺浏览器用户数据目录
│   ├── fingerprints/               # 指纹快照
│   └── checkpoints/                # LangGraph checkpoint
│
├── logs/                           # 日志
├── Dockerfile                      # 容器镜像（Playwright base + 多阶段）
├── docker-compose.yml              # 多店铺隔离编排
├── entrypoint.sh                   # 容器角色化入口（ROLE=api/worker/migrate）
├── pyproject.toml
├── .env.example
└── README.md
```

## 三、核心难点：反自动化检测解决方案

### 3.1 底层环境反检测体系

从浏览器特征、指纹、网络三维度消除自动化痕迹。

#### 3.1.1 浏览器自动化特征抹除

基于 Playwright 定制 Chromium，移除可被检测的自动化标识。核心通过 `add_init_script` 在每个文档加载前注入覆盖脚本：

```python
# engine/stealth.py
"""反检测脚本注入：在每个页面上下文初始化前执行，抹除自动化特征。"""

STEALTH_JS = r"""
// 1. navigator.webdriver -> undefined
try {
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
} catch (e) {}

// 2. 移除 cdp_* 等自动化全局变量
['cdc_adoQpoasnfa76pfcZLmcfl_Array', 'cdc_adoQpoasnfa76pfcZLmcfl_Promise',
 'cdc_adoQpoasnfa76pfcZLmcfl_Symbol'].forEach(function (k) {
    if (k in window) { delete window[k]; }
});

// 3. plugins / mimeTypes 对齐真实 Chrome
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const make = (name, filename, desc) => ({
            name, filename, description: desc, length: 1,
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
    if (p === 37445) return 'Intel Inc.';            // UNMASKED_VENDOR_WEBGL
    if (p === 37446) return 'Intel Iris OpenGL Engine'; // UNMASKED_RENDERER_WEBGL
    return getParameter.call(this, p);
};

// 7. 拦截自动化探测（检测 Object.defineProperty 是否被改写）
//    通过 Proxy 包装，使 toString() 返回原生形态
"""

LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--no-default-browser-check",
    "--disable-dev-shm-usage",
    # 不再传 --enable-automation
]


def apply_stealth(context):
    """对浏览器上下文注入反检测脚本。"""
    context.add_init_script(STEALTH_JS)
```

#### 3.1.2 店铺级指纹隔离与持久化

每店铺绑定固定指纹，持久化到 `data_persist/fingerprints/<shop_id>.json`，不随机生成：

```python
# engine/fingerprint.py
"""店铺指纹管理：每店铺固定指纹，持久化，模拟真实固定设备。"""
import json, random
from pathlib import Path
from dataclasses import dataclass, asdict

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    # ... 与目标市场匹配的真实 UA
]

@dataclass
class Fingerprint:
    shop_id: str
    user_agent: str
    viewport: dict            # {"width": 1920, "height": 1080}
    device_scale_factor: float
    locale: str               # "zh-CN"
    timezone_id: str          # "Asia/Shanghai"
    platform: str             # "Win32"
    hardware_concurrency: int # 8
    color_depth: int          # 24
    webgl_vendor: str
    webgl_renderer: str
    canvas_noise: float       # Canvas 指纹微扰种子
    fonts: list               # 已安装字体列表

class FingerprintManager:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get(self, shop_id: str) -> Fingerprint:
        fp_file = self.base_dir / f"{shop_id}.json"
        if fp_file.exists():
            return Fingerprint(**json.loads(fp_file.read_text("utf-8")))
        # 仅首次生成，之后固定
        fp = self._generate(shop_id)
        fp_file.write_text(json.dumps(asdict(fp), ensure_ascii=False, indent=2), "utf-8")
        return fp

    def _generate(self, shop_id: str) -> Fingerprint:
        # 从真实设备参数池中选取，避免离群值
        return Fingerprint(
            shop_id=shop_id,
            user_agent=random.choice(UA_POOL),
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=1.0,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            platform="Win32",
            hardware_concurrency=8,
            color_depth=24,
            webgl_vendor="Intel Inc.",
            webgl_renderer="Intel(R) UHD Graphics 630",
            canvas_noise=random.uniform(-0.0001, 0.0001),
            fonts=["Microsoft YaHei", "SimSun", "Arial", "Calibri"],
        )
```

#### 3.1.3 浏览器环境封装（用户数据目录 + 代理）

```python
# engine/browser.py
"""浏览器环境封装：独立用户数据目录、代理、指纹、Cookie 持久化。"""
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext
from engine.stealth import apply_stealth, LAUNCH_ARGS
from engine.fingerprint import FingerprintManager, Fingerprint

class BrowserEnv:
    def __init__(self, profile_dir: Path, fingerprint: Fingerprint, proxy: dict | None):
        self.profile_dir = profile_dir
        self.fingerprint = fingerprint
        self.proxy = proxy
        self._pw = None
        self._browser = None
        self.context: BrowserContext | None = None

    async def start(self):
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=False,                # 风控场景要求有头，必要时用 xvfb
            args=LAUNCH_ARGS,
            proxy=self.proxy,
            user_agent=self.fingerprint.user_agent,
            viewport=self.fingerprint.viewport,
            locale=self.fingerprint.locale,
            timezone_id=self.fingerprint.timezone_id,
            color_scheme="light",
            ignore_default_args=["--enable-automation"],
        )
        apply_stealth(self._browser)
        self.context = self._browser
        return self

    async def persist_cookies(self):
        """任务结束前持久化 Cookie/LocalStorage，保留登录态。"""
        # persistent_context 自动持久化到 user_data_dir，此处可追加显式快照
        if self.context:
            await self.context.storage_state(
                path=str(self.profile_dir / "storage_state.json")
            )

    async def close(self):
        if self.context:
            await self.persist_cookies()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
```

### 3.2 滑块验证码自动绕过方案

针对缺口匹配型滑块，采用 **CV 识别 + 拟人轨迹**，通过率目标 ≥90%，无需打码平台。

#### 3.2.1 缺口定位（YOLOv8 轻量化）

```python
# engine/captcha/slider_detect.py
"""基于 YOLOv8 的滑块缺口横坐标检测，精度误差目标 ≤2 像素。"""
from ultralytics import YOLO
import numpy as np

class SliderDetector:
    def __init__(self, model_path: str, conf: float = 0.5):
        self.model = YOLO(model_path)
        self.conf = conf

    def detect_gap_x(self, image: np.ndarray) -> int | None:
        """返回缺口左边界横坐标（相对于画布），未检出返回 None。"""
        results = self.model(image, conf=self.conf, verbose=False)
        for box in results[0].boxes:
            # 类别 0 = 缺口，类别 1 = 滑块
            if int(box.cls[0]) == 0:
                x1 = int(box.xyxy[0][0])
                return x1
        return None
```

#### 3.2.2 拟人滑动轨迹生成

```python
# engine/captcha/slider_track.py
"""贝塞尔曲线轨迹：先加速→后减速→微小过冲→小幅回退。"""
import numpy as np, random

def _bezier(points, n=40):
    points = np.array(points, dtype=float)
    t = np.linspace(0, 1, n)
    while len(points) > 1:
        points = (1 - t)[:, None] * points[:-1] + t[:, None] * points[1:]
    return points[0]

def gen_track(distance: int) -> list[tuple[float, float, float]]:
    """生成 [(x, y, dt_ms), ...] 轨迹点。"""
    overshoot = distance + random.randint(2, 6)        # 过冲
    control_x = [0, distance * 0.3, distance * 0.7, overshoot, distance]
    control_y = [0, random.uniform(-1, 1), random.uniform(-2, 2),
                 random.uniform(-1, 1), random.uniform(-1, 1)]
    xs = _bezier(control_x, n=50)
    ys = _bezier(control_y, n=50)
    # 速度：先快后慢，dt 递增
    dts = np.linspace(8, 22, len(xs)).astype(int) + np.random.randint(-3, 4, len(xs))
    track = [(float(xs[i]), float(ys[i]), int(max(5, dts[i]))) for i in range(len(xs))]
    # 末端回退修正
    track.append((float(distance), 0.0, random.randint(30, 60)))
    return track
```

#### 3.2.3 滑块编排（原生鼠标事件派发）

```python
# engine/captcha/slider.py
"""滑块验证码编排：截图→定位缺口→派发原生鼠标事件拖动。"""
from playwright.async_api import Page
from engine.captcha.slider_detect import SliderDetector
from engine.captcha.slider_track import gen_track
from engine.humanize import random_sleep

class SliderSolver:
    def __init__(self, detector: SliderDetector):
        self.detector = detector

    async def solve(self, page: Page, slider_handle_selector: str,
                    canvas_selector: str, max_retry: int = 3) -> bool:
        for attempt in range(max_retry):
            canvas = await page.query_selector(canvas_selector)
            shot = await canvas.screenshot()
            import numpy as np; from PIL import Image; import io
            img = np.array(Image.open(io.BytesIO(shot)))
            gap_x = self.detector.detect_gap_x(img)
            if gap_x is None:
                await random_sleep(0.5, 1.0)
                continue
            handle = await page.query_selector(slider_handle_selector)
            box = await handle.bounding_box()
            start_x, start_y = box["x"] + box["width"]/2, box["y"] + box["height"]/2
            # 原生鼠标事件，不直接改 style/left
            await page.mouse.move(start_x, start_y)
            await page.mouse.down()
            for dx, dy, dt in gen_track(gap_x - int(box["x"])):
                await page.mouse.move(start_x + dx, start_y + dy)
                await page.wait_for_timeout(dt)
            await page.mouse.up()
            await random_sleep(0.8, 1.5)
            if await self._verify_passed(page):
                return True
        return False

    async def _verify_passed(self, page: Page) -> bool:
        # 子类按平台实现：检测成功文案/弹窗消失/URL 变化
        raise NotImplementedError
```

> 降级策略：连续 3 次识别失败，返回 `SkillStatus.HUMAN_REQUIRED`，由工作流触发飞书人工介入。

### 3.3 登录态失效与短信验证码处理

采用 **态保持优先 + 人机协同兜底** 双层方案。

#### 3.3.1 登录态长效保持

- 任务结束完整持久化浏览器上下文（`storage_state.json`），7 天内免重登。
- 任务前登录态预校验：访问商家后台首页，检测是否跳转登录页。
- 控制单店铺每日登录次数 ≤1 次。

#### 3.3.2 短信验证码人机协同（LangGraph interrupt）

利用 LangGraph `interrupt` 将任务挂起，等待飞书回复恢复：

```python
# agent/nodes.py（节选：短信验证码节点）
from langgraph.types import interrupt
from skills.captcha import CaptchaSkill, SkillStatus

def handle_sms_captcha(state: TaskState) -> TaskState:
    skill = CaptchaSkill(config=get_config(), browser=state["browser_env"])
    # 1. 自动点击「获取验证码」
    skill.trigger_sms_send()
    # 2. 飞书机器人通知运营人员，附带 shop_name / task_id
    skill.notify_human_for_sms(state["task_id"], state["target_shop"])
    # 3. 挂起等待运营人员在飞书回复验证码（5 分钟超时由外部 watcher 处理）
    code = interrupt({"task_id": state["task_id"], "wait": "sms_code"})
    # 4. 恢复后填入并提交
    result = skill.submit_sms_code(code)
    state["captcha_type"] = "sms"
    state["error_msg"] = "" if result.status == SkillStatus.SUCCESS else result.error
    return state
```

恢复执行由 API 触发（见 7.4）：

```python
# agent/runner.py（节选）
from langgraph.types import Command
def resume_with_sms_code(thread_id: str, code: str):
    graph = build_graph()
    graph.invoke(Command(resume=code), config={"configurable": {"thread_id": thread_id}})
```

合规备选：自有手机号可配置短信转发网关，自动拉取验证码填入，全程免人工（需确保手机号所有权合规）。

### 3.4 全链路行为拟人化策略

```python
# engine/humanize.py
"""拟人化行为：贝塞尔鼠标轨迹、逐字符输入、正态分布等待。"""
import asyncio, random, math

async def random_sleep(mean: float = 2.0, sigma: float = 0.5):
    """正态分布等待，拒绝固定间隔。"""
    t = max(0.1, random.gauss(mean, sigma))
    await asyncio.sleep(t)

async def human_move(mouse, x: float, y: float, steps: int = 25):
    """贝塞尔曲线鼠标移动。"""
    sx, sy = await mouse.position() if False else (0, 0)  # 由调用方传起点
    ctrl = [(sx, sy), (sx + (x-sx)*0.3, sy + (y-sy)*0.1),
            (sx + (x-sx)*0.7, sy + (y-sy)*0.9), (x, y)]
    for i in range(steps + 1):
        t = i / steps
        # 三次贝塞尔
        bx = ((1-t)**3*ctrl[0][0] + 3*(1-t)**2*t*ctrl[1][0]
              + 3*(1-t)*t**2*ctrl[2][0] + t**3*ctrl[3][0])
        by = ((1-t)**3*ctrl[0][1] + 3*(1-t)**2*t*ctrl[1][1]
              + 3*(1-t)*t**2*ctrl[2][1] + t**3*ctrl[3][1])
        await mouse.move(bx, by)
        await asyncio.sleep(random.uniform(0.005, 0.02))

async def human_click(page, selector: str):
    el = await page.query_selector(selector)
    box = await el.bounding_box()
    cx, cy = box["x"] + box["width"]/2, box["y"] + box["height"]/2
    await human_move(page.mouse, cx, cy)
    await asyncio.sleep(random.uniform(0.1, 0.3))   # 悬停
    await page.mouse.click(cx, cy)
    await random_sleep(0.3, 0.1)

async def human_type(page, selector: str, text: str):
    """逐字符输入，间隔 50-200ms，偶发删除重输。"""
    await human_click(page, selector)
    for ch in text:
        await page.keyboard.type(ch)
        await asyncio.sleep(random.uniform(0.05, 0.2))
        if random.random() < 0.02 and ch != text[-1]:   # 2% 概率删重输
            await page.keyboard.press("Backspace")
            await asyncio.sleep(random.uniform(0.1, 0.3))
            await page.keyboard.type(ch)
```

策略参数汇总：

- 鼠标：贝塞尔轨迹，点击前 100-300ms 悬停，点击后随机停顿。
- 键盘：逐字符 50-200ms 随机，偶发删除重输。
- 浏览：编辑中插入随机滚动、停顿，禁止毫秒级连续操作。
- 步骤间隔：正态分布（均值 2s，标准差 0.5s）。
- 单商品上架总时长：3-8 分钟，对齐人工。

## 四、Agent 工作流编排设计

基于 LangGraph 构建状态机工作流，支持分支判断、重试、异常降级，全流程可追溯。

### 4.1 全局状态定义

```python
# agent/state.py
from typing import TypedDict, Optional, Any
from enum import Enum

class CaptchaType(str, Enum):
    NONE = "none"
    SLIDE = "slide"
    SMS = "sms"

class TaskStatus(str, Enum):
    PENDING = "待执行"
    RUNNING = "执行中"
    SUCCESS = "成功"
    FAILED = "失败"
    HUMAN = "待人工"

class TaskState(TypedDict, total=False):
    task_id: str                  # 任务唯一 ID
    product_code: str             # 商品编码
    target_shop: str              # 目标店铺标识
    product_material: dict        # ERP 检索到的商品素材
    sku_price_list: list          # SKU 与价格列表
    browser_env: Any              # 浏览器环境实例
    login_status: bool            # 登录状态
    captcha_type: str             # 验证码类型：none/slide/sms
    shelf_result: dict            # 上架结果
    retry_count: int              # 当前重试次数
    error_msg: str                # 错误信息
    status: str                   # 任务状态（见 TaskStatus）
    platform_item_id: str         # 平台返回商品 ID
    node_trace: list              # 节点执行轨迹（节点名/状态/时间戳）
```

### 4.2 工作流图构建

```python
# agent/graph.py
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
from agent.state import TaskState
from agent import nodes, routes

def build_graph(checkpointer: PostgresSaver | None = None):
    g = StateGraph(TaskState)

    # 节点注册
    g.add_node("init", nodes.init_task)
    g.add_node("erp_search", nodes.erp_material_search)
    g.add_node("sku_match", nodes.sku_price_match)
    g.add_node("env_start", nodes.start_env)
    g.add_node("login_check", nodes.check_login)
    g.add_node("login", nodes.do_login)
    g.add_node("captcha", nodes.handle_captcha)
    g.add_node("listing", nodes.do_listing)
    g.add_node("verify", nodes.verify_result)
    g.add_node("feishu_sync", nodes.sync_feishu)
    g.add_node("cleanup", nodes.cleanup)

    # 线性边
    g.set_entry_point("init")
    g.add_edge("init", "erp_search")
    g.add_edge("erp_search", "sku_match")
    g.add_edge("sku_match", "env_start")
    g.add_edge("env_start", "login_check")
    g.add_edge("login", "captcha")
    g.add_edge("captcha", "listing")           # 仅验证码通过分支会到这里
    g.add_edge("feishu_sync", "cleanup")
    g.add_edge("cleanup", END)

    # 条件边
    g.add_conditional_edges("login_check", routes.route_login, {
        "logged_in": "listing",
        "need_login": "login",
    })
    g.add_conditional_edges("captcha", routes.route_captcha, {
        "ok": "listing",
        "human": "feishu_sync",   # interrupt 挂起，同步挂起态后由人工恢复
        "fail": "feishu_sync",
    })
    g.add_conditional_edges("verify", routes.route_verify, {
        "success": "feishu_sync",
        "retry": "listing",
        "fail": "feishu_sync",
    })

    return g.compile(checkpointer=checkpointer)
```

### 4.3 节点函数与条件路由

```python
# agent/nodes.py
"""工作流节点：每个节点调用对应 Skill，更新 TaskState，追加 node_trace。"""
from datetime import datetime
from agent.state import TaskState, TaskStatus, CaptchaType
from skills import (EnvManagerSkill, ErpMaterialSkill, SkuPriceSkill,
                    ListingSkill, CaptchaSkill, FeishuSyncSkill)
from langgraph.types import interrupt
from config.settings import get_config

def _trace(state: TaskState, node: str, status: str, extra: str = ""):
    state.setdefault("node_trace", []).append({
        "node": node, "status": status,
        "ts": datetime.utcnow().isoformat(), "extra": extra,
    })
    return state

def init_task(state: TaskState) -> TaskState:
    state["retry_count"] = state.get("retry_count", 0)
    state["status"] = TaskStatus.RUNNING.value
    state["captcha_type"] = CaptchaType.NONE.value
    return _trace(state, "init", "ok", f"task_id={state['task_id']}")

def erp_material_search(state: TaskState) -> TaskState:
    skill = ErpMaterialSkill(config=get_config())
    res = skill.execute(product_code=state["product_code"])
    if res.status.value != 0:
        state["error_msg"] = res.error or "erp search failed"
        return _trace(state, "erp_search", "fail", state["error_msg"])
    state["product_material"] = res.data["material"]
    return _trace(state, "erp_search", "ok")

def sku_price_match(state: TaskState) -> TaskState:
    skill = SkuPriceSkill(config=get_config())
    res = skill.execute(skus=state["product_material"]["skus"],
                        shop_id=state["target_shop"])
    state["sku_price_list"] = res.data["sku_price_list"]
    return _trace(state, "sku_match", "ok")

def start_env(state: TaskState) -> TaskState:
    skill = EnvManagerSkill(config=get_config())
    res = skill.execute(shop_id=state["target_shop"], action="start")
    state["browser_env"] = res.data["browser_env"]
    return _trace(state, "env_start", "ok")

def check_login(state: TaskState) -> TaskState:
    skill = EnvManagerSkill(config=get_config(), browser=state["browser_env"])
    state["login_status"] = skill.check_login_state()
    return _trace(state, "login_check", "ok", f"login={state['login_status']}")

def do_login(state: TaskState) -> TaskState:
    skill = EnvManagerSkill(config=get_config(), browser=state["browser_env"])
    res = skill.login()
    state["login_status"] = res.status.value == 0
    return _trace(state, "login", "ok" if state["login_status"] else "fail")

def handle_captcha(state: TaskState) -> TaskState:
    skill = CaptchaSkill(config=get_config(), browser=state["browser_env"])
    ctype = skill.detect_type()
    state["captcha_type"] = ctype
    if ctype == CaptchaType.SMS.value:
        skill.trigger_sms_send()
        skill.notify_human_for_sms(state["task_id"], state["target_shop"])
        code = interrupt({"task_id": state["task_id"], "wait": "sms_code"})
        res = skill.submit_sms_code(code)
    else:  # slide
        res = skill.solve_slider()
    state["error_msg"] = "" if res.status.value == 0 else (res.error or "captcha fail")
    return _trace(state, "captcha", "ok" if res.status.value == 0 else "fail")

def do_listing(state: TaskState) -> TaskState:
    skill = ListingSkill(config=get_config(), browser=state["browser_env"])
    res = skill.execute(material=state["product_material"],
                        sku_price_list=state["sku_price_list"],
                        shop_id=state["target_shop"])
    state["shelf_result"] = res.data
    return _trace(state, "listing", "ok" if res.status.value == 0 else "fail")

def verify_result(state: TaskState) -> TaskState:
    skill = ListingSkill(config=get_config(), browser=state["browser_env"])
    res = skill.verify(state["shelf_result"])
    state["shelf_result"] = res.data
    state["platform_item_id"] = res.data.get("platform_item_id", "")
    return _trace(state, "verify", "ok" if res.status.value == 0 else "fail")

def sync_feishu(state: TaskState) -> TaskState:
    skill = FeishuSyncSkill(config=get_config())
    skill.execute(task=state)   # 内部按 status 写入总表/日志表/SKU 明细
    return _trace(state, "feishu_sync", "ok")

def cleanup(state: TaskState) -> TaskState:
    skill = EnvManagerSkill(config=get_config(), browser=state.get("browser_env"))
    if state.get("browser_env"):
        skill.execute(shop_id=state["target_shop"], action="recycle")
    state["status"] = state.get("status", TaskStatus.FAILED.value)
    return _trace(state, "cleanup", "ok")
```

```python
# agent/routes.py
"""条件路由：根据状态决定下一节点。"""
from agent.state import TaskState, TaskStatus

def route_login(state: TaskState) -> str:
    return "logged_in" if state.get("login_status") else "need_login"

def route_captcha(state: TaskState) -> str:
    if not state.get("error_msg"):
        return "ok"
    return "human" if state.get("captcha_type") == "sms" else "fail"

def route_verify(state: TaskState) -> str:
    result = state.get("shelf_result", {})
    if result.get("verified"):
        return "success"
    if state.get("retry_count", 0) < 3:
        state["retry_count"] = state.get("retry_count", 0) + 1
        return "retry"
    return "fail"
```

### 4.4 执行入口与 checkpoint 恢复

```python
# agent/runner.py
"""图执行入口：支持新任务执行与挂起任务恢复。"""
from langgraph.types import Command
from agent.graph import build_graph
from agent.state import TaskStatus
from data.db import get_checkpointer
from integrations.feishu.bot import FeishuBot

def run_task(task_id: str, product_code: str, target_shop: str):
    graph = build_graph(checkpointer=get_checkpointer())
    initial = {"task_id": task_id, "product_code": product_code,
               "target_shop": target_shop, "status": TaskStatus.PENDING.value}
    return graph.invoke(initial, config={"configurable": {"thread_id": task_id}})

def resume_with_sms_code(task_id: str, code: str):
    """运营人员飞书回复验证码后调用，恢复挂起任务。"""
    graph = build_graph(checkpointer=get_checkpointer())
    return graph.invoke(Command(resume=code),
                        config={"configurable": {"thread_id": task_id}})
```

### 4.5 重试与降级机制

- **上架失败**：非风控类错误最多重试 3 次，间隔递增（1min/3min/5min），由 `route_verify` 控制。
- **验证码失败**：滑块最多 3 次（见 3.2.3），失败转人工；短信超时任务挂起，人工处理后可恢复。
- **风控触发**：账号限制提示立即终止该店铺所有任务，飞书告警，人工排查（见 8.2）。

## 五、业务 Skill 设计与落地

### 5.1 Skill 通用规范

```python
# skills/base.py
"""Skill 基类与统一返回结构。"""
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Any, Optional

class SkillStatus(IntEnum):
    SUCCESS = 0          # 成功
    RETRYABLE = 1        # 可重试失败
    FATAL = 2            # 不可重试失败
    HUMAN_REQUIRED = 3   # 需人工介入

@dataclass
class SkillResult:
    status: SkillStatus
    data: dict = field(default_factory=dict)
    error: Optional[str] = None
    error_code: Optional[str] = None       # 见第十节错误码体系

class BaseSkill:
    name: str = ""
    def __init__(self, config, browser=None):
        self.config = config
        self.browser = browser

    def execute(self, **kwargs) -> SkillResult:
        raise NotImplementedError

    def _ok(self, data: dict | None = None) -> SkillResult:
        return SkillResult(SkillStatus.SUCCESS, data or {})

    def _retry(self, error: str, code: str = "") -> SkillResult:
        return SkillResult(SkillStatus.RETRYABLE, error=error, error_code=code)

    def _fatal(self, error: str, code: str = "") -> SkillResult:
        return SkillResult(SkillStatus.FATAL, error=error, error_code=code)

    def _human(self, error: str, code: str = "") -> SkillResult:
        return SkillResult(SkillStatus.HUMAN_REQUIRED, error=error, error_code=code)
```

状态码：0=成功，1=可重试失败，2=不可重试失败，3=需人工介入。依赖统一注入浏览器环境实例与配置。

### 5.2 核心 Skill 详细设计

#### 5.2.1 ERP 素材检索 Skill

- **功能**：从 ERP 商品素材库检索指定编码的商品素材（主图、详情图、规格参数、描述）。
- **输入**：`product_code`、`material_type`
- **输出**：`{material: {title, image_urls, spec_params, detail_text, skus}}`
- **实现**：ERP 支持数据库直连则 SQL 查询 + 对象存储拉图；仅网页端则浏览器登录检索下载；素材预处理（尺寸适配、压缩）。

```python
# skills/erp_material.py
from skills.base import BaseSkill, SkillResult
from integrations.erp.erp_client import ErpClient
from data.minio_client import MinioClient

class ErpMaterialSkill(BaseSkill):
    name = "erp_material"

    def execute(self, product_code: str, material_type: str = "all", **_) -> SkillResult:
        try:
            client = ErpClient(self.config.erp)
            if client.supports_db():
                meta = client.query_by_code(product_code)
                images = [MinIO(self.config).presign(u) for u in meta["image_urls"]]
            else:
                meta = client.scrape_by_code(product_code)   # 走浏览器
                images = meta["image_urls"]
            material = {
                "title": meta["title"],
                "image_urls": images,
                "spec_params": meta["spec_params"],
                "detail_text": meta["detail_text"],
                "skus": meta["skus"],
            }
            material = self._preprocess(material)
            return self._ok({"material": material})
        except ConnectionError as e:
            return self._retry(str(e), "ERP_1001")
        except Exception as e:
            return self._fatal(str(e), "ERP_2001")

    def _preprocess(self, material: dict) -> dict:
        # 图片尺寸适配各平台、压缩；此处占位
        return material
```

#### 5.2.2 SKU 价格匹配 Skill

- **功能**：根据目标店铺价格策略，为多 SKU 匹配售价、库存。
- **输入**：`skus`、`shop_id`
- **输出**：`{sku_price_list: [{sku, price, stock, status}]}`
- **实现**：读店铺价格配置（基础价 + 加价比例/活动价）计算售价；对接库存数据过滤无库存 SKU。

```python
# skills/sku_price.py
from skills.base import BaseSkill
from data.repositories.shop_repo import ShopRepo

class SkuPriceSkill(BaseSkill):
    name = "sku_price"

    def execute(self, skus: list, shop_id: str, **_) -> SkillResult:
        shop = ShopRepo().get(shop_id)
        strategy = shop.price_strategy          # {base, markup_ratio, promo}
        stock_map = self._fetch_stock(skus)     # 对接库存系统
        out = []
        for sku in skus:
            stock = stock_map.get(sku["sku_code"], 0)
            if stock <= 0:
                continue                        # 过滤无库存
            price = round(sku["cost"] * strategy["markup_ratio"]
                          + strategy.get("base", 0), 2)
            if strategy.get("promo"):
                price = min(price, strategy["promo"])
            out.append({"sku": sku["sku_code"], "price": price,
                        "stock": stock, "status": "pending"})
        if not out:
            return self._fatal("no sku with stock", "SKU_2001")
        return self._ok({"sku_price_list": out})

    def _fetch_stock(self, skus):
        return {s["sku_code"]: s.get("stock", 0) for s in skus}
```

#### 5.2.3 店铺上架 Skill

- **功能**：在目标店铺后台完成商品信息填充并提交上架。
- **输入**：`material`、`sku_price_list`、`shop_id`
- **输出**：`{submitted, platform_item_id, error}`
- **实现**：跳转发布页 → 选类目 → 填标题/卖点/详情 → 传主图详情图 → 批量加 SKU 规格/价格/库存 → 设运费/上架时间 → 提交 → 校验跳转。

```python
# skills/listing.py
from skills.base import BaseSkill
from engine.humanize import human_click, human_type, random_sleep

class ListingSkill(BaseSkill):
    name = "listing"
    PUBLISH_URL = "{base}/item/publish"          # 子类按平台覆写

    def execute(self, material: dict, sku_price_list: list, shop_id: str, **_):
        page = self.browser.context.pages[0]
        try:
            base = self.config.shops[shop_id].base_url
            page.goto(self.PUBLISH_URL.format(base=base))
            self._select_category(page, material["spec_params"])
            self._fill_basic(page, material)
            self._upload_images(page, material["image_urls"])
            self._fill_skus(page, sku_price_list)
            self._set_shipping(page)
            self._submit(page)
            return self._ok({"submitted": True})
        except Exception as e:
            return self._retry(str(e), "LST_1001")

    def verify(self, shelf_result: dict):
        page = self.browser.context.pages[0]
        try:
            page.goto(f"{self.config.shops[self.browser.shop_id].base_url}/item/list")
            verified, pid = self._inspect_list(page, shelf_result)
            return self._ok({"verified": verified, "platform_item_id": pid})
        except Exception as e:
            return self._retry(str(e), "LST_1002")

    # 以下方法子类按平台实现具体选择器
    def _select_category(self, page, spec): ...
    def _fill_basic(self, page, material): ...
    def _upload_images(self, page, urls): ...
    def _fill_skus(self, page, sku_price_list): ...
    def _set_shipping(self, page): ...
    def _submit(self, page): ...
    def _inspect_list(self, page, shelf_result): ...
```

#### 5.2.4 验证码处理 Skill

- **功能**：统一处理各类验证码，封装滑块识别、短信协同。
- **输入**：`captcha_type`、页面元素句柄
- **输出**：`{verified}`、状态码
- **实现**：自动识别类型，滑块走 CV + 轨迹；短信走飞书人工协同（interrupt）。

```python
# skills/captcha.py
from skills.base import BaseSkill
from engine.captcha.slider import SliderSolver
from engine.captcha.slider_detect import SliderDetector
from integrations.feishu.bot import FeishuBot

class CaptchaSkill(BaseSkill):
    name = "captcha"
    MAX_SLIDE_RETRY = 3

    def detect_type(self) -> str:
        page = self.browser.context.pages[0]
        if page.query_selector(self.config.selectors.sms_input):
            return "sms"
        if page.query_selector(self.config.selectors.slider_canvas):
            return "slide"
        return "none"

    def solve_slider(self):
        detector = SliderDetector(self.config.captcha.slider_model)
        solver = SliderSolver(detector)
        page = self.browser.context.pages[0]
        ok = solver.solve(page, self.config.selectors.slider_handle,
                          self.config.selectors.slider_canvas, self.MAX_SLIDE_RETRY)
        if ok:
            return self._ok({"verified": True})
        return self._human("slide failed 3 times", "CAP_3001")

    def trigger_sms_send(self):
        page = self.browser.context.pages[0]
        page.click(self.config.selectors.sms_send_btn)

    def notify_human_for_sms(self, task_id: str, shop_id: str):
        FeishuBot(self.config.feishu).notify_sms(task_id, shop_id)

    def submit_sms_code(self, code: str):
        page = self.browser.context.pages[0]
        page.fill(self.config.selectors.sms_input, code)
        page.click(self.config.selectors.sms_submit)
        return self._ok({"verified": True})
```

#### 5.2.5 飞书多维表格同步 Skill

- **功能**：将上架任务全链路数据写入飞书多维表格。
- **输入**：`task`（TaskState）、上架结果、店铺信息
- **输出**：同步结果
- **实现**：调用飞书多维表格 API 写入指定表；支持增量更新、失败重试。详见第六节。

```python
# skills/feishu_sync.py
from skills.base import BaseSkill
from integrations.feishu.bitable import BitableWriter

class FeishuSyncSkill(BaseSkill):
    name = "feishu_sync"

    def execute(self, task, **_):
        writer = BitableWriter(self.config.feishu)
        try:
            # 1. 总表更新状态
            writer.upsert_task(task)
            # 2. 日志表追加节点轨迹
            writer.append_logs(task["task_id"], task.get("node_trace", []))
            # 3. SKU 明细批量写入（仅上架成功）
            if task.get("shelf_result", {}).get("verified"):
                writer.batch_insert_skus(task["task_id"], task["sku_price_list"])
            return self._ok({"synced": True})
        except Exception as e:
            # 本地落盘 + 定时补偿，避免数据丢失
            self._fallback_to_local(task, str(e))
            return self._retry(str(e), "FS_1001")
```

#### 5.2.6 环境管理 Skill

- **功能**：统一管理店铺浏览器环境的创建、启动、回收、Cookie 持久化。
- **输入**：`shop_id`、`action`（start/recycle/reset）
- **输出**：浏览器环境实例
- **实现**：按 shop_id 加载指纹、代理、Cookie，启动隔离上下文；任务结束持久化 Cookie 并回收。

```python
# skills/env_manager.py
from skills.base import BaseSkill
from engine.browser import BrowserEnv
from engine.fingerprint import FingerprintManager
from pathlib import Path
from config.settings import get_config

class EnvManagerSkill(BaseSkill):
    name = "env_manager"

    def execute(self, shop_id: str, action: str = "start", **_):
        if action == "start":
            return self._start(shop_id)
        if action == "recycle":
            return self._recycle()
        if action == "reset":
            return self._reset(shop_id)
        return self._fatal("unknown action", "ENV_2001")

    def _start(self, shop_id: str):
        cfg = get_config()
        shop = cfg.shops[shop_id]
        fp = FingerprintManager(Path("data_persist/fingerprints")).get(shop_id)
        proxy = {"server": shop.proxy.server,
                 "username": shop.proxy.username, "password": shop.proxy.password}
        env = BrowserEnv(Path(f"data_persist/browser_profiles/{shop_id}"), fp, proxy)
        env.shop_id = shop_id
        import asyncio
        asyncio.get_event_loop().run_until_complete(env.start()) \
            if False else None   # 实际在异步节点内 await env.start()
        return self._ok({"browser_env": env})

    def check_login_state(self) -> bool:
        # 访问商家后台首页，检测是否跳转登录页
        ...

    def login(self):
        ...

    def _recycle(self):
        if self.browser:
            import asyncio
            asyncio.get_event_loop().run_until_complete(self.browser.close()) \
                if False else None
        return self._ok({"recycled": True})

    def _reset(self, shop_id: str):
        # 清空 profile 目录，下次启动重新登录
        ...
```

> 说明：节点函数运行在异步工作流中，`await env.start()` 在节点内直接调用，上文的同步分支仅为结构示意。

## 六、飞书多维表格数据对接

### 6.1 数据模型设计

飞书多维表格设 3 张工作表：

#### 表 1：商品上架任务总表

| 字段名 | 类型 | 说明 |
| --- | --- | --- |
| 任务 ID | 文本 | 唯一标识 |
| 商品编码 | 文本 | ERP 商品编码 |
| 商品名称 | 文本 | 商品标题 |
| 目标店铺 | 单选 | 对应店铺名称 |
| SKU 数量 | 数字 | 上架 SKU 总数 |
| 上架状态 | 单选 | 待执行 / 执行中 / 成功 / 失败 / 待人工 |
| 平台商品 ID | 文本 | 上架成功后返回的平台 ID |
| 执行时间 | 日期 | 任务完成时间 |
| 错误备注 | 多行文本 | 失败原因说明 |
| 操作人 | 人员 | 触发人 / 处理人 |

#### 表 2：SKU 价格明细表

| 字段名 | 类型 | 说明 |
| --- | --- | --- |
| 关联任务 ID | 文本 | 关联主表 |
| SKU 规格 | 文本 | 如：颜色 - 尺码 |
| 售价 | 数字 | 店铺上架价格 |
| 库存 | 数字 | 上架库存 |
| 上架状态 | 单选 | 成功 / 失败 |

#### 表 3：运行日志表

| 字段名 | 类型 | 说明 |
| --- | --- | --- |
| 日志 ID | 文本 | 唯一标识 |
| 关联任务 ID | 文本 | 关联主表 |
| 节点名称 | 文本 | 工作流节点 |
| 执行状态 | 单选 | 成功 / 失败 |
| 时间戳 | 日期 | 执行时间 |
| 日志详情 | 多行文本 | 详细执行信息 |

### 6.2 飞书 API 客户端与多维表格写入

```python
# integrations/feishu/client.py
"""飞书 API 客户端：Token 管理（tenant_access_token 缓存 + 自动续期）。"""
import time, requests

class FeishuClient:
    BASE = "https://open.feishu.cn/open-apis"
    def __init__(self, app_id: str, app_secret: str):
        self.app_id, self.app_secret = app_id, app_secret
        self._token, self._expire_at = None, 0

    def tenant_token(self) -> str:
        if self._token and time.time() < self._expire_at - 60:
            return self._token
        r = requests.post(f"{self.BASE}/auth/v3/tenant_access_token/internal",
                          json={"app_id": self.app_id, "app_secret": self.app_secret})
        d = r.json()
        self._token = d["tenant_access_token"]
        self._expire_at = time.time() + d["expire"]
        return self._token

    def request(self, method: str, path: str, **kw):
        kw.setdefault("headers", {"Authorization": f"Bearer {self.tenant_token()}"})
        return requests.request(method, f"{self.BASE}{path}", **kw).json()
```

```python
# integrations/feishu/bitable.py
"""多维表格读写：总表 upsert、日志追加、SKU 批量写入。"""
from integrations.feishu.client import FeishuClient

class BitableWriter:
    def __init__(self, cfg):  # cfg: {app_id, app_secret, app_token, table_id_*}
        self.cfg = cfg
        self.cli = FeishuClient(cfg["app_id"], cfg["app_secret"])

    def _upsert(self, table_id, fields):
        return self.cli.request("POST",
            f"/bitable/v1/apps/{self.cfg['app_token']}/tables/{table_id}/records",
            json={"fields": fields})

    def upsert_task(self, task):
        fields = {
            "任务 ID": task["task_id"],
            "商品编码": task["product_code"],
            "目标店铺": task["target_shop"],
            "上架状态": task.get("status", "执行中"),
            "平台商品 ID": task.get("platform_item_id", ""),
            "错误备注": task.get("error_msg", ""),
        }
        return self._upsert(self.cfg["table_id_task"], fields)

    def append_logs(self, task_id, traces):
        for i, tr in enumerate(traces):
            self._upsert(self.cfg["table_id_log"], {
                "日志 ID": f"{task_id}-{i}",
                "关联任务 ID": task_id,
                "节点名称": tr["node"],
                "执行状态": "成功" if tr["status"] == "ok" else "失败",
                "时间戳": tr["ts"],
                "日志详情": tr.get("extra", ""),
            })

    def batch_insert_skus(self, task_id, sku_list):
        # 飞书批量新增接口，最多 1000 条/次
        records = [{"fields": {
            "关联任务 ID": task_id,
            "SKU 规格": s["sku"],
            "售价": s["price"],
            "库存": s["stock"],
            "上架状态": s["status"],
        }} for s in sku_list]
        return self.cli.request("POST",
            f"/bitable/v1/apps/{self.cfg['app_token']}/tables/{self.cfg['table_id_sku']}/records/batch_create",
            json={"records": records})
```

```python
# integrations/feishu/bot.py
"""飞书机器人告警：验证码人工介入、风控触发、任务失败。"""
from integrations.feishu.client import FeishuClient

class FeishuBot:
    def __init__(self, cfg):
        self.cli = FeishuClient(cfg["app_id"], cfg["app_secret"])
        self.chat_id = cfg["notify_chat_id"]

    def _send(self, text):
        return self.cli.request("POST", "/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            json={"receive_id": self.chat_id,
                  "msg_type": "text", "content": f'{{"text":"{text}"}}'})

    def notify_sms(self, task_id, shop_id):
        self._send(f"[待人工] 短信验证码\n店铺:{shop_id}\n任务:{task_id}\n请回复验证码")

    def notify_risk(self, shop_id, msg):
        self._send(f"[风控告警] 店铺:{shop_id} 触发账号限制\n{msg}\n已暂停该店铺所有任务")

    def notify_fail(self, task_id, shop_id, err):
        self._send(f"[任务失败] 店铺:{shop_id} 任务:{task_id}\n原因:{err}")
```

### 6.3 多维表格路径配置

```yaml
# config/feishu.yaml
app_id: "cli_xxxxxxxxxxxx"
app_secret: "xxxxxxxxxxxxxxxxxxxxxxxx"
app_token: "bascnxxxxxxxxxxxxxxxxxx"   # 多维表格应用标识
table_id_task: "tblxxxxxxxx"           # 任务总表
table_id_sku: "tblyyyyyyyy"            # SKU 明细表
table_id_log: "tblzzzzzzzz"            # 日志表
notify_chat_id: "oc_xxxxxxxxxxxxxxxx"  # 告警群
```

### 6.4 一致性保障

写入失败自动重试 3 次；重试失败本地落盘 `logs/feishu_fallback/<task_id>.json`，由定时任务 `scripts/feishu_compensate.py` 补偿同步，避免数据丢失。

## 七、接口层与配置

### 7.1 全局配置

```python
# config/settings.py
from pydantic_settings import BaseSettings
from pydantic import Field
import yaml, pathlib

class ProxyCfg:
    def __init__(self, server, username="", password=""):
        self.server, self.username, self.password = server, username, password

class ShopCfg:
    def __init__(self, data):
        self.__dict__.update(data)
        self.proxy = ProxyCfg(**data.get("proxy", {"server": ""}))

class Settings(BaseSettings):
    pg_dsn: str = "postgresql+psycopg://ec:ec@localhost:5432/ecagent"
    minio_endpoint: str = "localhost:9000"
    minio_access: str = "minioadmin"
    minio_secret: str = "minioadmin"
    headless: bool = False
    class Config:
        env_file = ".env"

_settings = None

def get_config() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.shops = _load_shops()
        _settings.feishu = _load_yaml("config/feishu.yaml")
    return _settings

def _load_shops():
    shops = {}
    for f in pathlib.Path("config/shops").glob("*.yaml"):
        d = yaml.safe_load(f.read_text("utf-8"))
        shops[d["shop_id"]] = ShopCfg(d)
    return shops

def _load_yaml(p):
    return yaml.safe_load(pathlib.Path(p).read_text("utf-8"))
```

### 7.2 店铺配置文件

```yaml
# config/shops/shop_example.yaml
shop_id: "shop_001"
shop_name: "示例店铺-平台A"
platform: "platform_a"            # 对应 ListingSkill 子类
base_url: "https://seller.example.com"
account:
  username: "shop001_account"
  password: "${SHOP001_PWD}"      # 从环境变量注入，避免硬编码
fingerprint:
  profile_dir: "data_persist/browser_profiles/shop_001"
proxy:
  server: "http://residential.proxy:8080"
  username: "shop001"
  password: "${SHOP001_PROXY_PWD}"
price_strategy:
  base: 0.0
  markup_ratio: 1.35
  promo: null
feishu_notify:
  chat_id: "oc_xxxxxxxx"
  operator_id: "ou_yyyyyyyy"      # 责任运营人员
selectors:                         # 平台相关选择器，供 Skill 复用
  sms_input: "input[name=smscode]"
  sms_send_btn: "#sendSmsBtn"
  sms_submit: "#submitBtn"
  slider_canvas: ".captcha-canvas"
  slider_handle: ".slider-btn"
```

> 新增店铺仅需添加一个 YAML，无需改代码，支持横向扩展。

### 7.3 REST API 接口

```python
# api/server.py
from fastapi import FastAPI
from api.routes import tasks, shops

def create_app():
    app = FastAPI(title="EcListingAgent API")
    app.include_router(tasks.router, prefix="/api")
    app.include_router(shops.router, prefix="/api")
    return app

app = create_app()
```

```python
# api/routes/tasks.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from agent.runner import run_task, resume_with_sms_code
from data.repositories.task_repo import TaskRepo

router = APIRouter()

class TaskCreateReq(BaseModel):
    product_code: str
    target_shop: str

class SmsResumeReq(BaseModel):
    code: str

@router.post("/tasks")
def create_task(req: TaskCreateReq):
    task_id = TaskRepo().create(req.product_code, req.target_shop)
    run_task(task_id, req.product_code, req.target_shop)   # 异步队列生产环境改 BackgroundTasks/Celery
    return {"task_id": task_id}

@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    t = TaskRepo().get(task_id)
    if not t:
        raise HTTPException(404, "task not found")
    return t

@router.post("/tasks/{task_id}/resume")
def resume(task_id: str, req: SmsResumeReq):
    resume_with_sms_code(task_id, req.code)
    return {"ok": True}
```

```python
# api/routes/shops.py
from fastapi import APIRouter
from config.settings import get_config

router = APIRouter()

@router.get("/shops")
def list_shops():
    return [{"shop_id": s.shop_id, "shop_name": s.shop_name}
            for s in get_config().shops.values()]
```

## 八、数据层设计

### 8.1 数据库模型

```python
# data/db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config.settings import get_config
from langgraph.checkpoint.postgres import PostgresSaver

_engine = create_engine(get_config().pg_dsn, pool_pre_ping=True)
Session = sessionmaker(_engine)

def get_checkpointer():
    saver = PostgresSaver.from_conn_string(get_config().pg_dsn)
    saver.setup()                 # 首次建表
    return saver
```

```python
# data/models.py
from sqlalchemy import Column, String, Integer, DateTime, JSON, Text
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime

class Base(DeclarativeBase): pass

class Task(Base):
    __tablename__ = "tasks"
    task_id = Column(String, primary_key=True)
    product_code = Column(String, index=True)
    target_shop = Column(String, index=True)
    status = Column(String, default="待执行")       # 见 TaskStatus
    platform_item_id = Column(String, default="")
    sku_count = Column(Integer, default=0)
    error_msg = Column(Text, default="")
    operator = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    extra = Column(JSON, default=dict)

class Shop(Base):
    __tablename__ = "shops"
    shop_id = Column(String, primary_key=True)
    shop_name = Column(String)
    platform = Column(String)
    base_url = Column(String)
    config_path = Column(String)
    proxy_server = Column(String)
    login_count_today = Column(Integer, default=0)
    last_login_at = Column(DateTime, nullable=True)
    risk_status = Column(String, default="normal")  # normal/limited

class RunLog(Base):
    __tablename__ = "run_logs"
    id = Column(String, primary_key=True)           # {task_id}-{i}
    task_id = Column(String, index=True)
    node = Column(String)
    status = Column(String)
    ts = Column(DateTime, default=datetime.utcnow)
    detail = Column(Text, default="")
```

### 8.2 对象存储

```python
# data/minio_client.py
from minio import Minio
from config.settings import get_config

class MinIO:
    def __init__(self, cfg):
        self.cli = Minio(cfg.minio_endpoint,
                         access_key=cfg.minio_access, secret_key=cfg.minio_secret,
                         secure=False)
        self.bucket = "ec-material"
        if not self.cli.bucket_exists(self.bucket):
            self.cli.make_bucket(self.bucket)

    def put(self, object_name, file_path):
        self.cli.fput_object(self.bucket, object_name, file_path)
        return f"{self.bucket}/{object_name}"

    def presign(self, object_name, expires=3600):
        from datetime import timedelta
        return self.cli.presigned_get_object(self.bucket, object_name, expires=timedelta(seconds=expires))
```

## 九、部署与运行方案

### 9.1 部署架构

Docker 容器化部署，环境隔离与快速扩缩容：

- 主服务容器：Agent 编排服务 + Skill 引擎 + 定时调度。
- 浏览器实例：每店铺独立浏览器运行环境，按需启动。
- 数据库容器：PostgreSQL 存配置与任务数据。
- 对象存储：MinIO 存商品素材。

### 9.2 Docker 配置

```dockerfile
# Dockerfile（根目录）
# 基础镜像：Playwright 官方（已含 Chromium + 系统依赖），省去手动装浏览器
# 多阶段构建：builder 装依赖，runtime 只拷必要产物，缩小镜像体积
FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy AS builder

ARG INSTALL_DEV=0
WORKDIR /build
COPY pyproject.toml README.md ./
COPY config/ ./config/
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && if [ "$INSTALL_DEV" = "1" ]; then \
         /opt/venv/bin/pip install -e ".[dev]"; \
       else \
         /opt/venv/bin/pip install -e .; \
       fi

FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy AS runtime
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY --from=builder /build/pyproject.toml /build/README.md ./
COPY agent/ skills/ engine/ data/ integrations/ api/ config/ scripts/ ./
COPY entrypoint.sh ./
RUN mkdir -p data_persist/browser_profiles data_persist/fingerprints \
             data_persist/slider_model logs/feishu_fallback \
    && chmod +x entrypoint.sh
EXPOSE 8000
# 角色化入口：ROLE=api（默认）/ worker / migrate
ENTRYPOINT ["./entrypoint.sh"]
```

```yaml
# docker-compose.yml（根目录）
# 服务拓扑：postgres / minio / api / worker-*（单店铺单容器隔离）
# 多店铺隔离：每店铺一个 worker 容器，独立 browser profile + 指纹卷
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ec
      POSTGRES_PASSWORD: ec
      POSTGRES_DB: ecagent
    volumes: [pg_data:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ec -d ecagent"]
      interval: 5s
      timeout: 3s
      retries: 10

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes: [minio_data:/data]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 5

  api:
    build: { context: ., dockerfile: Dockerfile }
    env_file:
      - path: .env            # 生产期存放真实密钥；dev 期可缺失
        required: false
    environment:
      PG_DSN: postgresql+psycopg://ec:ec@postgres:5432/ecagent
      MINIO_ENDPOINT: minio:9000
      HEADLESS: "true"
      ROLE: api               # entrypoint 据此初始化 DB + 启动 uvicorn
    ports: ["8000:8000"]
    depends_on:
      postgres: { condition: service_healthy }
      minio: { condition: service_healthy }
    restart: unless-stopped

  worker-taobao:
    build: { context: ., dockerfile: Dockerfile }
    env_file:
      - path: .env
        required: false
    environment:
      PG_DSN: postgresql+psycopg://ec:ec@postgres:5432/ecagent
      MINIO_ENDPOINT: minio:9000
      HEADLESS: "true"
      ROLE: worker
      TARGET_SHOP: shop_taobao
    depends_on:
      postgres: { condition: service_healthy }
      minio: { condition: service_healthy }
    volumes:
      - taobao_profile:/app/data_persist/browser_profiles
      - taobao_fingerprint:/app/data_persist/fingerprints
    restart: unless-stopped

volumes:
  pg_data:
  minio_data:
  taobao_profile:
  taobao_fingerprint:
```

```bash
# entrypoint.sh（根目录）
#!/bin/sh
# ROLE=api     : 等待 postgres → 初始化 DB → 启动 uvicorn
# ROLE=worker  : 等待 postgres → 启动单店铺 worker（需 TARGET_SHOP）
# ROLE=migrate : 等待 postgres → 仅初始化 DB 后退出
set -e
ROLE="${ROLE:-api}"
# 应用层就绪探测（最多 60s），补强 depends_on 健康检查
if [ -n "$PG_DSN" ]; then
    for i in $(seq 1 30); do
        python -c "from data.db import get_engine; get_engine().connect()" 2>/dev/null && break
        sleep 2
    done
fi
case "$ROLE" in
    migrate) python scripts/init_db.py ;;
    api)     python scripts/init_db.py && exec uvicorn api.server:app --host 0.0.0.0 --port 8000 ;;
    worker)  exec python -m agent.worker --shop "$TARGET_SHOP" ;;
esac
```

### 9.3 运行模式

1. **手动触发**：API 接口 / 飞书表单提交上架任务。
2. **定时任务**：定时扫描 ERP 待上架商品，自动生成上架任务。
3. **批量执行**：支持批量上架，自动控制并发（单店铺同时仅 1 个任务，避免风控）。

## 十、错误码体系

错误码格式 `<模块>_<类型><编号>`，类型：1=可重试、2=不可重试、3=需人工。

| 模块前缀 | 含义 | 示例 |
| --- | --- | --- |
| ERP_1xxx | ERP 素材检索（可重试） | ERP_1001 连接失败 |
| ERP_2xxx | ERP 素材检索（不可重试） | ERP_2001 商品编码不存在 |
| SKU_2xxx | SKU 价格匹配（不可重试） | SKU_2001 无库存 SKU |
| LST_1xxx | 店铺上架（可重试） | LST_1001 字段提交超时 |
| LST_2xxx | 店铺上架（不可重试） | LST_2001 类目不存在 |
| CAP_3xxx | 验证码（需人工） | CAP_3001 滑块 3 次失败 |
| CAP_1xxx | 验证码（可重试） | CAP_1001 缺口未检出 |
| ENV_1xxx | 环境管理（可重试） | ENV_1001 代理连接失败 |
| ENV_2xxx | 环境管理（不可重试） | ENV_2001 指纹配置缺失 |
| FS_1xxx | 飞书同步（可重试） | FS_1001 写入限流 |
| RISK_3xxx | 风控（需人工） | RISK_3001 账号被限制 |

错误码在 `SkillResult.error_code` 中返回，由编排层据类型决定重试 / 降级 / 人工，并写入飞书日志表。

## 十一、监控与运维

### 11.1 结构化日志

```python
# 统一 JSON 日志，按 task_id 串联全链路
import logging, json, sys

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "ts": self.formatTime(record), "level": record.levelname,
            "logger": record.name, "msg": record.getMessage(),
            "task_id": getattr(record, "task_id", ""),
            "shop_id": getattr(record, "shop_id", ""),
            "node": getattr(record, "node", ""),
        }, ensure_ascii=False)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
```

每节点执行详情与页面截图存 `logs/<task_id>/`，可通过任务 ID 追溯。

### 11.2 监控项

1. **运行监控**：全链路日志采集，任务 ID 追溯每节点执行详情与页面截图。
2. **风控监控**：统计各店铺验证码触发频率、登录失败次数，超阈值飞书告警；账号限制立即终止该店铺所有任务（`Shop.risk_status=limited`）。
3. **异常告警**：任务失败、风控触发、人工介入需求实时飞书机器人通知。
4. **登录态巡检**：`scripts/login_patrol.py` 每日定时巡检所有店铺登录态，提前发现失效。

## 十二、开发阶段规划

| 阶段 | 目标 | 交付物 |
| --- | --- | --- |
| P0 地基 | 工程骨架 + 数据层 + 配置 | 目录结构、DB schema、配置加载、Docker 起服务 |
| P1 引擎 | 浏览器环境 + 反检测 + 拟人化 | BrowserEnv、stealth、fingerprint、humanize，单店铺能稳定登录并保活 |
| P2 Skill | 6 个核心 Skill | ERP/SKU/Listing/Captcha/FeishuSync/EnvManager 可独立调试 |
| P3 编排 | LangGraph 工作流 + HITL | graph 跑通单店铺单商品全链路，interrupt 短信协同可用 |
| P4 风控对抗 | 滑块 CV + 风控监控 | YOLOv8 训练 + 轨迹，滑块通过率 ≥90%，风控告警与店铺熔断 |
| P5 运维 | 多店铺并发 + 监控巡检 | 批量执行、并发控制、登录态巡检、日志归档 |

## 十三、风险与合规说明

1. **账号风险**：拟人化操作降低风控概率，但无法完全规避平台检测，极端情况存在账号被限制风险，建议先用小号测试验证。
2. **合规边界**：本方案仅用于自身合法店铺的运营辅助，禁止用于恶意批量铺货、侵权商品上架等违规行为，使用者需自行承担对应平台规则责任。
3. **迭代适配**：平台反作弊策略持续更新，需定期迭代反检测引擎与验证码识别模型，保障可用性。
4. **凭证安全**：店铺账号、代理密码、飞书 secret 等敏感信息须通过环境变量注入，禁止入库代码与配置明文。

---

附：命名约定速查

| 概念 | 命名 | 位置 |
| --- | --- | --- |
| 全局状态 | `TaskState` | agent/state.py |
| 工作流图 | `build_graph` | agent/graph.py |
| 节点函数 | `init_task` / `erp_material_search` / ... | agent/nodes.py |
| 条件路由 | `route_login` / `route_captcha` / `route_verify` | agent/routes.py |
| Skill 基类 | `BaseSkill` / `SkillResult` / `SkillStatus` | skills/base.py |
| Skill 实现 | `ErpMaterialSkill` / `ListingSkill` / ... | skills/*.py |
| 浏览器环境 | `BrowserEnv` | engine/browser.py |
| 反检测 | `apply_stealth` / `STEALTH_JS` | engine/stealth.py |
| 指纹 | `FingerprintManager` / `Fingerprint` | engine/fingerprint.py |
| 滑块 | `SliderDetector` / `SliderSolver` / `gen_track` | engine/captcha/ |
| 飞书 | `FeishuClient` / `BitableWriter` / `FeishuBot` | integrations/feishu/ |
| 错误码 | `<模块>_<类型><编号>` | 见第十节 |
