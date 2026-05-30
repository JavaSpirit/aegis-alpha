from __future__ import annotations

from aegis_alpha.models import SignalEvidence, SignalMetadata


def unavailable_metadata(*, source_field: str, timestamp: str, limitation: str) -> SignalMetadata:
    return SignalMetadata(
        source="jvquant.semantic_query",
        source_field=source_field,
        timestamp=timestamp,
        confidence="unavailable",
        usable_for_grading=False,
        limitations=[limitation],
        evidence=[
            SignalEvidence(
                authority="internal_inference",
                source="aegis_alpha.adapters.jvquant",
                detail=limitation,
                observed_at=timestamp,
            )
        ],
    )


def build_second_board_data_quality(
    *,
    speed_timestamp: str,
    speed_window: str,
    has_exact_speed_window: bool,
    has_exact_multi_speed_windows: bool,
    query_timestamp: str,
    has_capital_flow: bool,
    has_auction_data: bool,
    has_theme_tags: bool,
    has_break_reseal_data: bool,
    has_max_seal_data: bool,
    has_seal_data: bool,
    has_orderbook_rows: bool,
    orderbook_timestamp: str,
    minute_replay_used: bool,
    minute_replay_timestamp: str,
    minute_replay_bar_count: int,
) -> dict[str, SignalMetadata]:
    semantic_query_doc = SignalEvidence(
        authority="official_doc",
        source="https://jvquant.com/wiki/",
        detail="jvQuant documentation lists semantic analysis database and comprehensive data query capabilities.",
        observed_at=query_timestamp,
    )
    level_queue_doc = SignalEvidence(
        authority="official_doc",
        source="https://jvquant.com/wiki/",
        detail="jvQuant documentation lists沪深Level2千档盘口队列 / level queue capabilities.",
        observed_at=query_timestamp,
    )
    minute_replay_doc = SignalEvidence(
        authority="official_doc",
        source="https://jvquant.com/wiki/%E6%95%B0%E6%8D%AE%E5%BA%93/%E6%B2%AA%E6%B7%B1%E5%88%86%E6%97%B6%E6%95%B0%E6%8D%AE.html",
        detail="jvQuant documentation lists mode=minute minute replay data with time, latest price, average price, and volume fields.",
        observed_at=query_timestamp,
    )
    speed_source = "jvquant.minute_replay" if minute_replay_used else "jvquant.semantic_query"
    speed_source_field = (
        "client.minute(mode=minute) bars recalculated into 1m/3m/5m/10m speeds"
        if minute_replay_used
        else "5分钟涨幅/区间涨跌幅"
    )
    speed_evidence = (
        [
            minute_replay_doc,
            SignalEvidence(
                authority="internal_inference",
                source="aegis_alpha.adapter",
                detail=(
                    "Aegis Alpha recalculates speed windows from jvQuant minute replay bars; "
                    f"minute_replay_bar_count={minute_replay_bar_count}."
                ),
                observed_at=minute_replay_timestamp or query_timestamp,
            ),
        ]
        if minute_replay_used
        else [
            semantic_query_doc,
            SignalEvidence(
                authority="observed_probe",
                source="docs/JVQUANT_FIELD_MAP.md",
                detail=(
                    f"Observed jvQuant speed field returned a parseable window: {speed_window}."
                    if has_exact_speed_window
                    else "Observed jvQuant speed field returned without a parseable window."
                ),
                observed_at=speed_timestamp,
            ),
            SignalEvidence(
                authority="internal_inference",
                source="aegis_alpha.adapter",
                detail="Confidence is high only when a provider window is parsed; otherwise medium.",
                observed_at=query_timestamp,
            ),
        ]
    )
    return {
        "five_min_speed": SignalMetadata(
            source=speed_source,
            source_field=speed_source_field,
            timestamp=speed_timestamp,
            confidence="high" if has_exact_speed_window else "medium",
            usable_for_grading=True,
            limitations=[
                f"window={speed_window}",
                (
                    "Speed was independently recalculated from minute replay bars."
                    if minute_replay_used
                    else (
                        "Exact provider interval parsed from returned field name."
                        if has_exact_speed_window
                        else "Provider did not expose exact five-minute window start/end in the field name."
                    )
                ),
                (
                    "Still minute-level replay, not tick-by-tick realtime Level-2."
                    if minute_replay_used
                    else "Not independently recalculated from minute bars or ticks yet."
                ),
            ],
            evidence=speed_evidence,
        ),
        "capital_flow": SignalMetadata(
            source="jvquant.semantic_query",
            source_field="主力净额/大单净额/超大单净额 divided by 成交额",
            timestamp=query_timestamp,
            confidence="medium" if has_capital_flow else "low",
            usable_for_grading=True,
            limitations=[
                "Provider semantic aggregation, not Aegis Alpha tick-by-tick big-order classification.",
                "Zero may mean neutral flow or provider field unavailable for the candidate.",
            ],
            evidence=[
                semantic_query_doc,
                SignalEvidence(
                    authority="observed_probe",
                    source="docs/JVQUANT_FIELD_MAP.md",
                    detail="Observed jvQuant semantic query returns 主力净额 fields for current candidates.",
                    observed_at=query_timestamp,
                ),
                SignalEvidence(
                    authority="internal_inference",
                    source="aegis_alpha.adapter",
                    detail="Ratio is computed by Aegis Alpha as capital-flow amount divided by turnover.",
                    observed_at=query_timestamp,
                ),
            ],
        ),
        "multi_speed": SignalMetadata(
            source=speed_source,
            source_field=(
                "client.minute(mode=minute) bars recalculated into 1m/3m/5m/10m speeds"
                if minute_replay_used
                else "1分钟涨幅/3分钟涨幅/10分钟涨幅"
            ),
            timestamp=minute_replay_timestamp or query_timestamp,
            confidence="high" if has_exact_multi_speed_windows else "medium",
            usable_for_grading=True,
            limitations=[
                (
                    "Recalculated from jvQuant minute replay bars."
                    if minute_replay_used
                    else "Observed semantic-query interval fields; not independently recalculated from minute bars or ticks."
                ),
                "Aegis Alpha treats this as speed-structure context rather than a standalone decision signal.",
            ],
            evidence=[
                minute_replay_doc if minute_replay_used else semantic_query_doc,
                (
                    SignalEvidence(
                        authority="internal_inference",
                        source="aegis_alpha.adapter",
                        detail=(
                            "Aegis Alpha recalculates multi-speed structure from minute bars; "
                            f"minute_replay_bar_count={minute_replay_bar_count}."
                        ),
                        observed_at=minute_replay_timestamp or query_timestamp,
                    )
                    if minute_replay_used
                    else SignalEvidence(
                        authority="observed_probe",
                        source="docs/JVQUANT_CAPABILITY_MATRIX.md",
                        detail="Observed jvQuant semantic queries return 1m, 3m, and 10m interval speed fields.",
                        observed_at=query_timestamp,
                    )
                ),
                SignalEvidence(
                    authority="internal_inference",
                    source="aegis_alpha.adapter",
                    detail="Multi-speed structure is used to judge whether the latest pull is accelerating or fading.",
                    observed_at=query_timestamp,
                ),
            ],
        ),
        "auction_metrics": SignalMetadata(
            source="jvquant.semantic_query",
            source_field="集合竞价涨跌幅/集合竞价成交额/集合竞价换手率",
            timestamp=query_timestamp,
            confidence="medium" if has_auction_data else "unavailable",
            usable_for_grading=has_auction_data,
            limitations=[
                "Observed semantic-query fields, not official field-level definitions.",
                "Auction quality still needs calibration by market cap and float turnover.",
            ],
            evidence=[
                semantic_query_doc,
                SignalEvidence(
                    authority="observed_probe",
                    source="docs/JVQUANT_CAPABILITY_MATRIX.md",
                    detail="Observed jvQuant semantic query returns auction change, auction turnover, and auction turnover-rate fields.",
                    observed_at=query_timestamp,
                ),
            ],
        ),
        "theme_tags": SignalMetadata(
            source="jvquant.semantic_query",
            source_field="概念/个股题材",
            timestamp=query_timestamp,
            confidence="medium" if has_theme_tags else "unavailable",
            usable_for_grading=has_theme_tags,
            limitations=[
                "Observed concept/topic tags may not be normalized to Aegis Alpha's future theme taxonomy.",
                "Same-theme strength still requires group-level aggregation.",
            ],
            evidence=[
                semantic_query_doc,
                SignalEvidence(
                    authority="observed_probe",
                    source="docs/JVQUANT_CAPABILITY_MATRIX.md",
                    detail="Observed jvQuant semantic query returns concept and topic fields.",
                    observed_at=query_timestamp,
                ),
                SignalEvidence(
                    authority="internal_inference",
                    source="aegis_alpha.adapter",
                    detail="Concept and topic tags are context signals until a normalized theme-strength model exists.",
                    observed_at=query_timestamp,
                ),
            ],
        ),
        "seal_metrics": SignalMetadata(
            source="jvquant.semantic_query",
            source_field="涨停首次封板时间/涨停封单额/涨停封单量/涨停封成比",
            timestamp=query_timestamp,
            confidence="medium" if has_seal_data else "unavailable",
            usable_for_grading=has_seal_data,
            limitations=[
                "Provider semantic snapshot; Aegis Alpha does not yet verify whether this is current, max, or close seal amount.",
                "Missing values should not be interpolated.",
            ],
            evidence=[
                semantic_query_doc,
                SignalEvidence(
                    authority="observed_probe",
                    source="docs/JVQUANT_FIELD_MAP.md",
                    detail="Observed jvQuant semantic query returns first seal time, seal amount, seal volume, and seal-to-turnover fields.",
                    observed_at=query_timestamp,
                ),
                SignalEvidence(
                    authority="internal_inference",
                    source="aegis_alpha.adapter",
                    detail="Seal metrics are medium confidence until current/max/close seal semantics are confirmed from official docs or tick replay.",
                    observed_at=query_timestamp,
                ),
            ],
        ),
        "max_seal_metrics": SignalMetadata(
            source="jvquant.semantic_query",
            source_field="最大封单金额/最大封单量",
            timestamp=query_timestamp,
            confidence="medium" if has_max_seal_data else "unavailable",
            usable_for_grading=has_max_seal_data,
            limitations=[
                "Observed semantic-query fields; official exact max-seal semantics are not yet confirmed.",
                "Do not confuse max seal amount with current own-order queue position.",
            ],
            evidence=[
                semantic_query_doc,
                SignalEvidence(
                    authority="observed_probe",
                    source="docs/JVQUANT_CAPABILITY_MATRIX.md",
                    detail="Observed jvQuant semantic query maps max-seal wording to seal amount and seal volume fields.",
                    observed_at=query_timestamp,
                ),
                SignalEvidence(
                    authority="internal_inference",
                    source="aegis_alpha.adapter",
                    detail="Max-seal metrics are medium confidence until official or replay evidence confirms the exact window.",
                    observed_at=query_timestamp,
                ),
            ],
        ),
        "break_reseal_metrics": SignalMetadata(
            source="jvquant.semantic_query",
            source_field="炸板次数/涨停回封次数/涨停最终封板时间",
            timestamp=query_timestamp,
            confidence="medium" if has_break_reseal_data else "unavailable",
            usable_for_grading=has_break_reseal_data,
            limitations=[
                "Observed semantic-query fields; not yet cross-checked with tick or replay data.",
                "Break/reseal counts should reduce confidence when nonzero until strategy calibration exists.",
            ],
            evidence=[
                semantic_query_doc,
                SignalEvidence(
                    authority="observed_probe",
                    source="docs/JVQUANT_CAPABILITY_MATRIX.md",
                    detail="Observed jvQuant semantic query returns break-board count, reseal count, and final seal time fields.",
                    observed_at=query_timestamp,
                ),
                SignalEvidence(
                    authority="internal_inference",
                    source="aegis_alpha.adapter",
                    detail="Break and reseal metrics are used as risk context, not deterministic rejection rules yet.",
                    observed_at=query_timestamp,
                ),
            ],
        ),
        "orderbook_queue": SignalMetadata(
            source="jvquant.level_queue",
            source_field="bid/ask queue summary",
            timestamp=orderbook_timestamp,
            confidence="medium" if has_orderbook_rows else "unavailable",
            usable_for_grading=has_orderbook_rows,
            limitations=[
                "Read-only orderbook summary, not own-order queue position.",
                "True queue position requires broker order and trade callbacks.",
            ],
            evidence=[
                level_queue_doc,
                SignalEvidence(
                    authority="observed_probe",
                    source="jvquant.level_queue",
                    detail=(
                        "Observed level_queue rows for this candidate."
                        if has_orderbook_rows
                        else "Provider returned no level_queue rows for this candidate at request time."
                    ),
                    observed_at=orderbook_timestamp,
                ),
                SignalEvidence(
                    authority="internal_inference",
                    source="aegis_alpha.adapter",
                    detail="Own-order queue position cannot be inferred without broker order/trade callbacks.",
                    observed_at=query_timestamp,
                ),
            ],
        ),
        "history_stats": SignalMetadata(
            source="aegis_alpha.placeholder",
            source_field="three_year_touch_limit_success_rate/three_year_sealed_next_day_gap_up_rate",
            timestamp=query_timestamp,
            confidence="placeholder",
            usable_for_grading=False,
            limitations=[
                "Historical second-board sample library is not implemented yet.",
                "Do not use zero placeholder rates as real historical probabilities.",
            ],
            evidence=[
                SignalEvidence(
                    authority="internal_inference",
                    source="aegis_alpha.placeholder",
                    detail="Historical fields are present in the contract but not yet backed by a sample database.",
                    observed_at=query_timestamp,
                ),
            ],
        ),
    }
