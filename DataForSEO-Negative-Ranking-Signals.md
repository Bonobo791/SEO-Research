# DataForSEO Negative Ranking Signals

Component source of truth for the `authority_proxy` control
(`build_authority_proxy` in `src/seo_rank/data/features.py`, spec
`analysis_spec.v1.2.yaml`).

Legend: `included: continuous` = domain median of page medians -> asinh ->
within-run z-score; `included: boolean` = domain rate -> within-run z-score
(no log). `negated` marks components where low/false is bad (polarity-flipped
so higher = worse before averaging). The composite is the negated mean of
available finite aligned z-scores, so higher `authority_proxy` = fewer negative
signals. A domain remains a complete model case when both controls are present;
an unavailable optional component does not discard the proxy.

Every signal registered in an `onpage_metric` family is excluded from this
control. It is an analyzed predictor, so including it would make the control a
mechanical part of the predictor. `test_authority_proxy.py` verifies the
exclusion list stays exactly aligned with `analysis_spec.v1.2.yaml`.

Included components:

- time_to_first_byte_ms — included: continuous
- largest_contentful_paint_ms — included: continuous
- cumulative_layout_shift — included: continuous
- first_input_delay_ms — included: continuous
- resource_errors_count — included: continuous
- render_blocking_scripts_count — included: continuous
- render_blocking_stylesheets_count — included: continuous
- meta_charset_consistency (false) — included: boolean, negated (1 - rate)
- canonical (absent) — included: boolean, negated (1 - rate)
- is_https (absent) — included: boolean, negated (1 - rate)
- has_meta_title (false) — included: boolean, negated (1 - rate)
- title_too_long, title_too_short, no_title, no_description, no_h1_tag,
  has_render_blocking_resources, duplicate_meta_tags, irrelevant_description,
  low_readability_rate, is_4xx_code, is_5xx_code, is_broken,
  no_content_encoding, high_loading_time, high_waiting_time, no_doctype,
  no_encoding_meta_tag, https_to_http_links, size_greater_than_3mb,
  has_meta_refresh_redirect, low_content_rate, large_page_size,
  irrelevant_title, irrelevant_meta_keywords, deprecated_html_tags,
  duplicate_title_tag, no_image_alt, broken_links, broken_resources,
  duplicate_description, duplicate_title — included: boolean

Excluded components:

- All registered `onpage_metric` signals — excluded: analyzed predictors.
- click_depth and from_sitemap — excluded: crawl metadata.
- total_dom_size, total_transfer_size, images_size, scripts_size, and
  stylesheets_size — excluded: already captured by site_scale.
