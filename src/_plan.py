"""连通检查计划

- 代理档位、候选顺序、每路预算与收尾裁决都住这里
- 本体只按计划里的公开数据跑通用调度
"""

from collections.abc import Mapping
from functools import partial

from finshin_sdk.domain import (
    ConfigValues,
    ConnectionPlan,
    PlanVerdict,
    ProbeChannel,
    ProbeOutcome,
    ProbeResult,
    ProbeRow,
    RowStatus,
)
from finshin_sdk.domain.config import ConfigPath, ConfigValue

from ._config import SOURCE
from ._messages import ConnectionMessage
from ._probe import PROXY_ITEM, run_channel

_MODE_ITEM = ConfigPath(source=SOURCE, section="proxy", key="proxy_mode")

# 通道探测预算（秒），与探针共用同一份
_PROBE_BUDGET = 9.0
_PROBE_BUDGET_DIRECT = 3.0

# 单路模式与档位串
_CFG = "cfg"
_SYS = "sys"
_DIRECT = "direct"
_AUTO = "auto"
_SINGLE_MODES = (_CFG, _SYS, _DIRECT)


def build_connection_plan(
    values: ConfigValues, token: str, *, system_proxy: str | None = None
) -> ConnectionPlan:
    """按当前配置造一份检查计划

    - 自动档按配置代理、系统代理、直连排序
    - 单路档只留选定一路，缺地址即缺席
    - 配置与系统代理同端点时去重
    """
    section = values.get("proxy") or {}
    mode = _mode_of(section)
    configured = str(section.get("proxy") or "").strip()
    system = (system_proxy or "").strip()

    rows: list[ProbeRow] = []
    channels: list[ProbeChannel] = []
    if mode == _AUTO:
        rows, channels = _auto_plan(configured, system, token)
    elif mode == _CFG:
        rows, channels = _single_plan(
            _CFG, configured, ConnectionMessage.MODE_CFG_ABSENT, token
        )
    elif mode == _SYS:
        rows, channels = _single_plan(
            _SYS, system, ConnectionMessage.MODE_SYS_ABSENT, token
        )
    else:
        rows, channels = _single_plan(_DIRECT, "", "", token)

    return ConnectionPlan(
        rows=tuple(rows),
        channels=tuple(channels),
        reuse_key=(mode, configured, system if mode in (_AUTO, _SYS) else ""),
        finish=partial(
            _finish,
            mode=mode,
            configured=configured,
            channels=tuple(channels),
            rows=tuple(rows),
        ),
    )


def _mode_of(section: Mapping[str, ConfigValue]) -> str:
    """取代理档位

    - 词表外的值按自动档处理，红点交给本地类型校验
    """
    mode = str(section.get("proxy_mode") or "").strip()
    return mode if mode in (_AUTO, *_SINGLE_MODES) else _AUTO


def _auto_plan(
    configured: str, system: str, token: str
) -> tuple[list[ProbeRow], list[ProbeChannel]]:
    """自动档的行与通道"""
    rows: list[ProbeRow] = []
    channels: list[ProbeChannel] = []

    if configured:
        rows.append(
            _channel_row(_CFG, ConnectionMessage.ROW_CFG, configured, token, channels)
        )
    else:
        rows.append(
            ProbeRow(
                row_id=_CFG,
                title=ConnectionMessage.ROW_CFG,
                status=RowStatus.FAIL,
                detail=ConnectionMessage.CFG_EMPTY,
            )
        )

    if not system:
        rows.append(
            ProbeRow(
                row_id=_SYS,
                title=ConnectionMessage.ROW_SYS,
                status=RowStatus.FAIL,
                detail=ConnectionMessage.SYS_UNAVAILABLE,
            )
        )
    elif configured and _same_endpoint(configured, system):
        rows.append(
            ProbeRow(
                row_id=_SYS,
                title=ConnectionMessage.ROW_SYS,
                status=RowStatus.SKIP,
                detail=ConnectionMessage.SYS_DEDUP,
            )
        )
    else:
        rows.append(
            _channel_row(_SYS, ConnectionMessage.ROW_SYS, system, token, channels)
        )

    rows.append(
        _channel_row(_DIRECT, ConnectionMessage.ROW_DIRECT, "", token, channels)
    )
    return rows, channels


def _single_plan(
    row_id: str, proxy: str, absent: str, token: str
) -> tuple[list[ProbeRow], list[ProbeChannel]]:
    """单路档的行与通道

    - 缺地址即一行缺席，不发探测
    """
    rows: list[ProbeRow] = []
    channels: list[ProbeChannel] = []
    if row_id == _DIRECT or proxy:
        rows.append(_channel_row(row_id, _row_title(row_id), proxy, token, channels))
    else:
        rows.append(
            ProbeRow(
                row_id=row_id,
                title=_row_title(row_id),
                status=RowStatus.FAIL,
                detail=absent,
            )
        )
    return rows, channels


def _channel_row(
    row_id: str,
    title: str,
    proxy: str,
    token: str,
    channels: list[ProbeChannel],
) -> ProbeRow:
    """造通道行并把该路探测排进计划"""
    budget = _PROBE_BUDGET_DIRECT if not proxy else _PROBE_BUDGET
    channels.append(
        ProbeChannel(
            row_id=row_id,
            label=_via_label(row_id, proxy),
            budget=budget,
            run=partial(run_channel, token, proxy, budget),
        )
    )
    return ProbeRow(row_id=row_id, title=title)


def _row_title(row_id: str) -> str:
    """行标题"""
    return {
        _CFG: ConnectionMessage.ROW_CFG,
        _SYS: ConnectionMessage.ROW_SYS,
        _DIRECT: ConnectionMessage.ROW_DIRECT,
    }[row_id]


def _via_label(row_id: str, proxy: str) -> str:
    """通道称谓"""
    if row_id == _DIRECT:
        return ConnectionMessage.VIA_DIRECT
    if row_id == _CFG:
        return ConnectionMessage.VIA_CFG.format(proxy=proxy)
    return ConnectionMessage.VIA_SYSTEM.format(proxy=proxy)


def _endpoint_key(url: str) -> tuple[str, str]:
    """提取代理地址的主机与端口"""
    body = url.strip().lower().split("://", 1)[-1].rstrip("/")
    host, _, port = body.rpartition(":")
    return host, port


def _same_endpoint(left: str, right: str) -> bool:
    """两个代理地址是否同一主机与端口"""
    return _endpoint_key(left) == _endpoint_key(right)


def _fault_row(mode: str) -> ConfigPath:
    """代理不通时标红哪一行

    - 代理项藏掉的档位，报错不能落在看不见的那行上
    """
    return PROXY_ITEM if mode in (_AUTO, _CFG) else _MODE_ITEM


def _finish(
    outcome: ProbeOutcome,
    *,
    mode: str,
    configured: str,
    channels: tuple[ProbeChannel, ...],
    rows: tuple[ProbeRow, ...],
) -> PlanVerdict:
    """收一轮结果并给出裁决

    - 有通道通过即按它的字段错误收尾，无错记通过或降级
    - 全挂时取优先级最高那一路的错误，多路聚成一句引导
    - 一个探测都没发的缺席轮，把缺席句标到该档看得见的那一行
    """
    if outcome.accepted is not None:
        return _accepted_verdict(outcome.accepted, mode, configured)

    failed = [(row, res) for row, res in outcome.results if not res.accepted]
    for _, result in failed:
        if PROXY_ITEM in result.field_errors:
            base = (
                ConnectionMessage.ALL_FAIL
                if len(channels) > 1
                else result.field_errors[PROXY_ITEM]
            )
            return PlanVerdict(
                field_errors={
                    _fault_row(mode): f"{base}\n{ConnectionMessage.PROXY_GUIDE}"
                },
                failure_detail=ConnectionMessage.DIAG_ADVICE_NONE,
            )
        if result.field_errors:
            return PlanVerdict(
                field_errors=dict(result.field_errors),
                failure_detail=ConnectionMessage.DIAG_ADVICE_NONE,
            )
        if result.detail:
            return PlanVerdict(
                field_errors={_fault_row(mode): result.detail},
                failure_detail=ConnectionMessage.DIAG_ADVICE_NONE,
            )
    if not channels:
        absent = next((row for row in rows if row.status == RowStatus.FAIL), None)
        if absent is not None:
            return PlanVerdict(
                field_errors={_fault_row(mode): absent.detail},
                failure_detail=ConnectionMessage.DIAG_ADVICE_NONE,
            )
    return PlanVerdict(failure_detail=ConnectionMessage.DIAG_ADVICE_NONE)


def _accepted_verdict(result: ProbeResult, mode: str, configured: str) -> PlanVerdict:
    """通道通过时的裁决"""
    if result.field_errors:
        return PlanVerdict(field_errors=dict(result.field_errors))

    effective = result.effective or ""
    via = (
        ConnectionMessage.VIA_DIRECT
        if not effective
        else ConnectionMessage.VIA_CFG.format(proxy=effective)
        if effective == configured
        else ConnectionMessage.VIA_SYSTEM.format(proxy=effective)
    )
    if mode == _AUTO and configured and effective != configured:
        return PlanVerdict(
            warning=ConnectionMessage.STALE.format(raw=configured, via=via)
        )
    return PlanVerdict(notice=ConnectionMessage.PASS.format(via=via))
