# 具身日报

每天自动抓取具身智能 / 机器人感知领域的新内容，打分筛选，生成「概念卡 + 自测题 + 前沿卡」，
推送到手机，同时在电脑上留一份可深读的队列。

给一个人用的，不是给一万人用的。

## 它每天做什么

1. 从 arXiv `cs.RO` / `cs.CV`、Hugging Face 每日论文、GitHub 新仓库抓取候选（约 100 条）
2. 用 SQLite 去重，只留没见过的
3. 规则打分（源权重 / 关键词 / 热度 / 新鲜度），再用 LLM 精排挑出真正值得读的那一条
4. 从课程骨架里取出「今天该学的那一格」，生成一张概念卡和两道题
5. 写进 `reading/queue.md`（电脑深读用）和 `output/recent7.json`（手机答题用）
6. 推一条通知到手机

## 快速开始

```bash
pip install -r requirements.txt
```

把 DeepSeek 的 key 放进环境变量（推荐）：

```powershell
setx JUSHEN_LLM_KEY "sk-..."
```

或者直接填进 `config.yaml` 的 `llm.api_key`——但**别把有 key 的文件提交上去**。

然后：

```
双击 启动.bat         抓取 + 生成 + 推送，打开 reading/queue.md
双击 手机访问.bat      起本地服务，手机在同一 WiFi 下打开
```

## 为什么用 YAML 而不是 TOML

因为目标环境是 Python 3.8，标准库没有 `tomllib`。同时 YAML 不受 TOML 那个
「标量必须写在所有子表之前」的坑影响。

## 目录

```
config.yaml        所有可调参数（源开关、权重、阈值、课程、推送）
curriculum/        课程骨架：perception.yaml（感知 10 格）/ control.yaml（电控 8 格）
engine/
  fetch.py         数据源适配器
  store.py         SQLite 去重 + 缓存
  rank.py          规则打分
  rerank.py        LLM 精排
  card.py          卡片生成（概念 / 题 / 前沿）
  llm.py           LLM 客户端（无 key 时自动降级）
  push.py          ntfy 推送
  curriculum.py    课程进度
run.py             主入口
server.py          本地静态服务（手机访问用）
web/index.html     手机答题页（单文件，无框架）
```

## 两个设计取舍

**手机做减法，电脑做加法。** 手机端只给 3 张卡（1 概念 + 2 题）和 1 条前沿，
7 天缓冲，超过就沉淀到电脑端。电脑端给全量候选和原始论文链接。

**宁可少推，不可乱推。** 某天没有内容越过阈值，就只推概念和题，不推前沿。

## 关于推送

用的是 [ntfy](https://ntfy.sh)，一个开源推送服务。在手机 App 里订阅 `config.yaml`
里 `push.topic` 那个主题名就能收到。**主题名等于密码**，所以带随机后缀。

Android 上要记得做三件事，否则收不到：电池「后台高耗电」、自启动、最近任务加锁。
国产 ROM 会杀后台长连接。

## 许可

MIT
