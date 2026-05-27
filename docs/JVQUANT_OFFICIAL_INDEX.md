# jvQuant Official Capability Index

This index records what Aegis Alpha currently treats as `official_doc` evidence. It only covers capabilities that appear in jvQuant official documentation. It does not claim that every semantic-query field has an official field-level definition.

## Officially Documented Capabilities

| Capability | Official source | What it supports | Boundary for Aegis Alpha |
|---|---|---|---|
| User manual / product navigation | https://jvquant.com/wiki/ | Official documentation tree, including market data, database data, comprehensive query, semantic query, and trading sections. | This proves capability categories exist, not detailed field semantics. |
| Semantic analysis database | https://jvquant.com/wiki/%E6%95%B0%E6%8D%AE%E5%BA%93/%E6%99%BA%E8%83%BD%E8%AF%AD%E4%B9%89%E6%9F%A5%E8%AF%A2.html | Natural-language-like database query with `mode=sql`, `query`, `sort_key`, `sort_type`, and `page`. | Officially supports semantic querying, but individual returned field meanings still need official field docs or observed probes. |
| Comprehensive data query | https://jvquant.com/wiki/%E6%95%B0%E6%8D%AE%E5%BA%93/%E7%BB%BC%E5%90%88%E6%95%B0%E6%8D%AE%E6%9F%A5%E8%AF%A2.html | Stock basic info, convertible bond info, index mapping, K-line data, semantic database, historical minute data download. | Capability category only; Aegis Alpha still probes field-level behavior. |
| K-line query | https://jvquant.com/wiki/%E6%95%B0%E6%8D%AE%E5%BA%93/%E6%B2%AA%E6%B7%B1K%E7%BA%BF%E6%9F%A5%E8%AF%A2.html | Security K-line data query. | Suitable for future self-calculated speed windows and historical follow-through checks. |
| Minute replay data | https://jvquant.com/wiki/%E6%95%B0%E6%8D%AE%E5%BA%93/%E6%B2%AA%E6%B7%B1%E5%88%86%E6%97%B6%E6%95%B0%E6%8D%AE.html | Minute replay query for a security over a period. | Candidate source for precise intraday windows; not yet integrated. |
| Historical market data download | https://jvquant.com/wiki/%E6%95%B0%E6%8D%AE%E5%BA%93/%E6%B2%AA%E6%B7%B1%E8%82%A1%E7%A5%A8%E5%8E%86%E5%8F%B2%E6%95%B0%E6%8D%AE%E4%B8%8B%E8%BD%BD.html | 2008-present market history download packages. | Candidate source for the second-board sample library; not yet integrated. |
| Level2 level queue | https://jvquant.com/wiki/%E6%95%B0%E6%8D%AE%E5%BA%93/%E6%B2%AA%E6%B7%B1Level2%E5%8D%83%E6%A1%A3%E7%9B%98%E5%8F%A3%E9%98%9F%E5%88%97%E6%9F%A5%E8%AF%A2.html | `mode=level_queue`, code-based queue query; documented return fields include `type`, `price`, `volume_count`, `queue_count`, and `queue_slice`. | This is official evidence for orderbook queue summaries, not for own-order queue position. |
| Level2 order queue | https://jvquant.com/wiki/%E6%95%B0%E6%8D%AE%E5%BA%93/%E6%B2%AA%E6%B7%B1Level2%E9%80%90%E7%AC%94%E5%A7%94%E6%89%98%E9%98%9F%E5%88%97%E6%9F%A5%E8%AF%A2.html | Level2 order queue query. | Candidate source for future tick/order-flow classification; not yet integrated. |
| Database service pricing | https://jvquant.com/wiki/%E5%B8%AE%E5%8A%A9/%E4%BB%B7%E6%A0%BC/%E6%95%B0%E6%8D%AE%E5%BA%93%E6%9C%8D%E5%8A%A1.html | Pricing categories for order queue, level queue, custom query, minute data, K-line, stock basics, convertible bond info, and historical minute data package. | Useful for cost modeling; not field semantics. |

## Evidence Rule

- `official_doc`: official jvQuant page documents a capability or field.
- `observed_probe`: Aegis Alpha called jvQuant and observed returned fields or sample values.
- `internal_inference`: Aegis Alpha inferred confidence, limitations, or scoring usability.

When official documentation confirms only a capability category, Aegis Alpha must not present that as official proof of a specific returned field's precise calculation semantics.
