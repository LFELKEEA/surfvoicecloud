# voice-cloud —— 云端语音（264 MB）

只做一件事：把文本发给火山「豆包声音复刻 2.0」，拿回音频。**本地不留任何大模型。**

| 项 | 值 |
|---|---|
| 端口 | **8767** |
| 音色 | `age12-cloud`（默认）/ `huayan`（piper 兜底） |
| 延迟 | 0.5~1.1 秒 |
| 成本 | 按字符计费（3 小时/天 ≈ 135 万字符/月，自己算账） |
| 体积 | 264 MB（含 119 MB 解释器 + 61 MB 兜底模型） |

## 启动

```bat
run.bat      :: 后台起服务
stop.bat     :: 停
```

## 验证

```bat
.venv\Scripts\python.exe -c "import urllib.request,json;b=json.dumps({'text':'你好'},ensure_ascii=False).encode();r=urllib.request.Request('http://127.0.0.1:8767/v1/speak/file',data=b,headers={'content-type':'application/json'});print(len(urllib.request.urlopen(r,timeout=60).read()),'bytes')"
```

或：

```bat
.venv\Scripts\python.exe scripts\say.py "一句话" --base http://127.0.0.1:8767
```

## 配置（`config.toml`）

```toml
[engine]
primary = "cloud"
fallbacks = ["piper"]        # 断网/欠费时用机械音顶上，不至于哑掉
cloud_app_id = "..."
cloud_access_key = "..."
cloud_resource = "seed-icl-2.0"   # 这个 id 不能改，换别的会 403

[voice]
default = "age12-cloud"
```

## 注意

- **首次装完要填三样**：AppID / Access Key / 音色 ID（设置页「云端包：密钥与音色」）。缺一样启动会被直接拦下——`voices/age12-cloud/voice.json` 里的 `speaker` 是空的。
- **必须联网**；火山不可用时只剩 piper 的机械音。
- 计费按字符，`max_chars` / 桥接侧的字数限制就是你的护栏。
- `resource` 必须是 `seed-icl-2.0`（换成 `seed-tts-2.0` 会报 55000000）。
- 音色是复刻 ID（`S_fxkbW5bj2`），不是本地文件；换音色要重新做复刻。

## 目录

```
config.toml     引擎/音色/凭据
voxd/           服务本体（和 voice-local 同一份代码）
voices/         age12-cloud、huayan
models/         piper 兜底模型（61 MB）
.venv/          精简环境（fastapi/uvicorn/numpy/soundfile/onnxruntime）
scripts/        say.py / doctor.py / audition.py
logs/           请求日志 requests.jsonl
```
