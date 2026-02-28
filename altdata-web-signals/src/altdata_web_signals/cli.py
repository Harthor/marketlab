"""CLI principal `signals`."""

from __future__ import annotations

import argparse
from argparse import ArgumentDefaultsHelpFormatter

from .config import PathConfig
from .dataset import build_research_dataset
from .fetchers.fear_greed import fetch_fng_signals
from .fetchers.onchain import fetch_onchain_signals
from .fetchers.reddit import fetch_reddit_signals
from .fetchers.rss import fetch_rss_signals
from .fetchers.rss_crypto import fetch_rss_crypto_signals
from .fetchers.trends import fetch_trend_series
from .fetchers.trends_btc import fetch_trends_btc_signals
from .fetchers.wikipedia import fetch_wiki_series


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _parse_join(value: str) -> str:
    if "=" in value:
        key, _, join = value.partition("=")
        if key.strip().lower() != "how":
            raise ValueError("Formato esperado: how=<inner|outer|left|right>")
        value = join
    value = value.strip().lower()
    if value not in {"inner", "outer", "left", "right"}:
        raise ValueError("join inválido: use inner|outer|left|right")
    return value


def _add_common(parser: argparse.ArgumentParser, *, config: PathConfig) -> None:
    parser.add_argument("--cache-dir", default=str(config.cache_root))
    parser.add_argument("--signals-root", default=str(config.signals_root))
    parser.add_argument("--freq", default="1d")


def cmd_wiki(args: argparse.Namespace) -> int:
    topics: list[str] = _split_csv(args.topics)
    if not topics:
        raise SystemExit("--topics no puede estar vacío")

    paths = fetch_wiki_series(
        topics=topics,
        start=args.start,
        end=args.end,
        signals_root=args.signals_root,
        freq=args.freq,
        cache_dir=args.cache_dir,
        project=args.project,
    )
    for out in paths:
        print(f"saved={out}")
    return 0


def cmd_rss(args: argparse.Namespace) -> int:
    keywords = _split_csv(args.keywords)
    if not keywords:
        raise SystemExit("--keywords no puede estar vacío")

    paths = fetch_rss_signals(
        feeds_file=args.feeds_file,
        keywords=keywords,
        start=args.start,
        end=args.end,
        use_regex=args.use_regex,
        signals_root=args.signals_root,
        freq=args.freq,
        cache_dir=args.cache_dir,
    )
    for out in paths:
        print(f"saved={out}")
    return 0


def cmd_trends(args: argparse.Namespace) -> int:
    try:
        paths = fetch_trend_series(
            keywords=_split_csv(args.keywords),
            start=args.start,
            end=args.end,
            country=args.country,
        )
    except Exception as exc:
        print(f"trends_skip: {exc}")
        return 0

    # TODO: en MVP opcional, dejar implementación de persistencia para cuando se habilite.
    # Aquí se imprime un resumen de lo obtenido para depuración.
    for key, frame in paths.items():
        print(f"trend_signal=signal_trends_{key} rows={len(frame)}")
    return 0


def cmd_fng(args: argparse.Namespace) -> int:
    paths = fetch_fng_signals(
        start=args.start,
        end=args.end,
        signals_root=args.signals_root,
        freq=args.freq,
        cache_dir=args.cache_dir,
        limit=args.limit,
    )
    for out in paths:
        print(f"saved={out}")
    return 0


def cmd_rss_crypto(args: argparse.Namespace) -> int:
    paths = fetch_rss_crypto_signals(
        start=args.start,
        end=args.end,
        signals_root=args.signals_root,
        freq=args.freq,
        cache_dir=args.cache_dir,
    )
    for out in paths:
        print(f"saved={out}")
    return 0


def cmd_reddit(args: argparse.Namespace) -> int:
    paths = fetch_reddit_signals(
        start=args.start,
        end=args.end,
        signals_root=args.signals_root,
        freq=args.freq,
        cache_dir=args.cache_dir,
    )
    for out in paths:
        print(f"saved={out}")
    return 0


def cmd_onchain(args: argparse.Namespace) -> int:
    paths = fetch_onchain_signals(
        start=args.start,
        end=args.end,
        signals_root=args.signals_root,
        freq=args.freq,
        cache_dir=args.cache_dir,
    )
    for out in paths:
        print(f"saved={out}")
    return 0


def cmd_trends_btc(args: argparse.Namespace) -> int:
    keywords = _split_csv(args.keywords) if args.keywords else None
    try:
        paths = fetch_trends_btc_signals(
            keywords=keywords,
            start=args.start,
            end=args.end,
            country=args.country,
            signals_root=args.signals_root,
            freq=args.freq,
            cache_dir=args.cache_dir,
        )
    except Exception as exc:
        print(f"trends_btc_skip: {exc}")
        return 0

    for out in paths:
        print(f"saved={out}")
    return 0


def cmd_build_dataset(args: argparse.Namespace) -> int:
    out = build_research_dataset(
        symbol=args.symbol,
        join=args.join,
        freq=args.freq,
        signals_root=args.signals_root,
        prices_root=args.prices_root,
        price_source=args.price_source,
        datasets_root=args.datasets_root,
        fill_method=args.fill_method,
        start=args.start,
        end=args.end,
    )
    print(f"saved={out}")
    print(f"meta={out.with_suffix('.meta.json')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    cfg = PathConfig.default()

    parser = argparse.ArgumentParser(
        prog="signals",
        description="Recolector de señales web y constructor de dataset de investigación",
        formatter_class=ArgumentDefaultsHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    wiki = sub.add_parser("wiki", help="Descarga señales de Wikipedia Pageviews")
    wiki.add_argument("--topics", required=True, help='Ej: "Bitcoin,Apple Inc."')
    wiki.add_argument("--start", required=True, help="YYYY-MM-DD")
    wiki.add_argument("--end", required=True, help="YYYY-MM-DD")
    wiki.add_argument("--project", default="en.wikipedia", help="Proyecto Wikipedia (por defecto: en.wikipedia)")
    _add_common(wiki, config=cfg)
    wiki.set_defaults(func=cmd_wiki)

    rss = sub.add_parser("rss", help="Genera señal diaria RSS por keywords")
    rss.add_argument("--feeds-file", required=True, help="Archivo YAML con URLs")
    rss.add_argument("--keywords", required=True, help='Ej: "bitcoin,apple,nvidia"')
    rss.add_argument("--start", required=True, help="YYYY-MM-DD")
    rss.add_argument("--end", required=True, help="YYYY-MM-DD")
    rss.add_argument("--use-regex", action="store_true", help="Interpretar keywords como regex")
    _add_common(rss, config=cfg)
    rss.set_defaults(func=cmd_rss)

    fng = sub.add_parser("fng", help="Fear & Greed Index (Alternative.me)")
    fng.add_argument("--start", default=None, help="YYYY-MM-DD (default: all history)")
    fng.add_argument("--end", default=None, help="YYYY-MM-DD (default: today)")
    fng.add_argument("--limit", type=int, default=0, help="API limit param (0 = all)")
    _add_common(fng, config=cfg)
    fng.set_defaults(func=cmd_fng)

    rss_crypto = sub.add_parser("rss-crypto", help="RSS crypto media + FinBERT sentiment")
    rss_crypto.add_argument("--start", default=None, help="YYYY-MM-DD (default: 1 year ago)")
    rss_crypto.add_argument("--end", default=None, help="YYYY-MM-DD (default: today)")
    _add_common(rss_crypto, config=cfg)
    rss_crypto.set_defaults(func=cmd_rss_crypto)

    reddit = sub.add_parser("reddit", help="Reddit crypto subreddits + FinBERT sentiment")
    reddit.add_argument("--start", default=None, help="YYYY-MM-DD (default: 60 days ago)")
    reddit.add_argument("--end", default=None, help="YYYY-MM-DD (default: today)")
    _add_common(reddit, config=cfg)
    reddit.set_defaults(func=cmd_reddit)

    trends_btc = sub.add_parser("trends-btc", help="Google Trends for BTC keywords")
    trends_btc.add_argument("--keywords", default=None, help='CSV (default: bitcoin,buy bitcoin,bitcoin crash,crypto)')
    trends_btc.add_argument("--start", default=None, help="YYYY-MM-DD (default: 5 years ago)")
    trends_btc.add_argument("--end", default=None, help="YYYY-MM-DD (default: today)")
    trends_btc.add_argument("--country", default="US")
    _add_common(trends_btc, config=cfg)
    trends_btc.set_defaults(func=cmd_trends_btc)

    onchain = sub.add_parser("onchain", help="On-chain signals (Mempool.space + DeFiLlama)")
    onchain.add_argument("--start", default=None, help="YYYY-MM-DD (default: 2020-01-01)")
    onchain.add_argument("--end", default=None, help="YYYY-MM-DD (default: today)")
    _add_common(onchain, config=cfg)
    onchain.set_defaults(func=cmd_onchain)

    trends = sub.add_parser("trends", help="Best-effort Google Trends (opcional)")
    trends.add_argument("--keywords", required=True)
    trends.add_argument("--start", required=True)
    trends.add_argument("--end", required=True)
    trends.add_argument("--country", default="US")
    trends.set_defaults(func=cmd_trends)

    build = sub.add_parser("build-dataset", help="Construye dataset research-ready")
    build.add_argument("--symbol", required=True)
    build.add_argument("--join", default="how=outer", type=_parse_join)
    build.add_argument("--freq", default="1d")
    build.add_argument("--prices-root", default=str(cfg.market_data_root))
    build.add_argument("--price-source", default="yfinance")
    build.add_argument("--fill-method", default="none", choices=["none", "forward", "backward"])
    build.add_argument("--datasets-root", default=str(cfg.datasets_root), help="Directorio raíz de data/datasets")
    build.add_argument("--start", default=None)
    build.add_argument("--end", default=None)
    build.add_argument("--signals-root", default=str(cfg.signals_root))
    build.set_defaults(func=cmd_build_dataset)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
