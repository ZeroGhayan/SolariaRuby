"""Gráfico multi-painel (PNG) para o Telegram, com matplotlib headless (Agg)."""
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from services.indicators import MA_COLORS, rsi, sma, stoch_rsi  # noqa: E402

PANELS = (("343m", (7, 21, 49, 77, 200, 231, 343)), ("686m", (7, 21, 49, 77, 200, 231, 343)),
          ("1d", (7, 21, 49, 77, 200, 231, 343)), ("2D", (7, 21, 77, 200, 231, 343)))


def _candles(ax, df):
    x = range(len(df))
    up = df["close"] >= df["open"]
    col = ["#26a69a" if u else "#ef5350" for u in up]
    ax.vlines(x, df["low"], df["high"], colors=col, linewidth=0.6)
    ax.bar(x, (df["close"] - df["open"]).abs().clip(lower=1e-9), bottom=df[["open", "close"]].min(axis=1),
           color=col, width=0.7)


def render(frames, title="", bars=120, panels=PANELS):
    """frames: {tf: DataFrame}. Retorna bytes PNG."""
    fig = plt.figure(figsize=(11, 8), dpi=90)  # 2x2 painéis (preço + osciladores)
    gs = fig.add_gridspec(4, 2, height_ratios=[3, 1, 3, 1], hspace=0.35, wspace=0.12)
    for i, (tf, lengths) in enumerate(panels[:4]):
        row, colx = (i // 2) * 2, i % 2
        ax = fig.add_subplot(gs[row, colx])
        ax2 = fig.add_subplot(gs[row + 1, colx], sharex=ax)
        df = frames.get(tf)
        if df is None or df.empty:
            ax.set_title(f"{tf}: sem dados", fontsize=9)
            continue
        full = df.reset_index(drop=True)
        start = max(0, len(full) - bars)
        view = full.iloc[start:].reset_index(drop=True)
        _candles(ax, view)
        for n in lengths:
            ma = sma(full["close"], n).iloc[start:].reset_index(drop=True)
            if ma.notna().any():
                ax.plot(ma, color=MA_COLORS.get(n, "black"), linewidth=0.9, label=f"MA{n}")
        ax.set_title(f"{tf} — {view['close'].iloc[-1]:,.0f}", fontsize=9)
        if ax.get_legend_handles_labels()[0]:
            ax.legend(fontsize=6, loc="upper left", ncol=4)
        ax.tick_params(labelsize=6)
        r = rsi(full["close"]).iloc[start:].reset_index(drop=True)
        k, d = stoch_rsi(full["close"])
        ax2.plot(r, color="purple", linewidth=0.8, label="RSI")
        ax2.plot(sma(rsi(full["close"]), 14).iloc[start:].reset_index(drop=True), color="gold",
                 linewidth=0.7, label="média RSI")
        ax2.plot(k.iloc[start:].reset_index(drop=True), color="dodgerblue", linewidth=0.6, label="StochK")
        ax2.axhline(26.21, color="red", linewidth=0.5, linestyle="--")
        ax2.axhline(70, color="gray", linewidth=0.4, linestyle=":")
        ax2.set_ylim(0, 100)
        ax2.tick_params(labelsize=6)
        ax2.legend(fontsize=5, loc="upper left", ncol=3)
        ticks = list(range(0, len(view), max(1, len(view) // 4)))
        ax2.set_xticks(ticks)
        ax2.set_xticklabels([pd.to_datetime(view["ts"].iloc[t], unit="ms").strftime("%d/%m") for t in ticks])
        plt.setp(ax.get_xticklabels(), visible=False)
    if title:
        fig.suptitle(title, fontsize=10)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
