from datetime import datetime

def parse_date(date_str: str) -> datetime:
    """Convert string (YYYY-MM-DD or DD/MM/YYYY) to datetime."""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            pass
    raise ValueError("Invalid date format. Use YYYY-MM-DD or DD/MM/YYYY")

def days_overlap(start1: datetime, end1: datetime, start2: datetime, end2: datetime) -> int:
    """Days of overlap between [start1, end1] and [start2, end2]."""
    start = max(start1, start2)
    end = min(end1, end2)
    if end <= start:
        return 0
    return (end - start).days

def validate_periods(buy_date: str, sell_date: str, periods: list):
    """
    基础校验：
    - 每段 start < end
    - 检查相邻段是否有 overlap 或 gap
    - 检查是否覆盖整个持有期
    返回 warnings 列表（字符串）
    """
    if not periods:
        raise ValueError("You must enter at least one usage period.")

    d_buy = parse_date(buy_date)
    d_sell = parse_date(sell_date)

    parsed = []
    for p in periods:
        label = p.get("label", "")
        s = parse_date(p["start"])
        e = parse_date(p["end"])

        if e <= s:
            raise ValueError(f"Period '{label}' end date must be AFTER start date.")

        parsed.append({"label": label, "start": s, "end": e})

    # 按开始日期排序
    parsed.sort(key=lambda x: x["start"])

    warnings = []

    # 检查起始/结束是否覆盖整个持有期
    if parsed[0]["start"] > d_buy:
        gap_days = (parsed[0]["start"] - d_buy).days
        warnings.append(
            f"There is a gap of {gap_days} days BEFORE the first period "
            f"(from {d_buy.date()} to {parsed[0]['start'].date()})."
        )
    if parsed[-1]["end"] < d_sell:
        gap_days = (d_sell - parsed[-1]["end"]).days
        warnings.append(
            f"There is a gap of {gap_days} days AFTER the last period "
            f"(from {parsed[-1]['end'].date()} to {d_sell.date()})."
        )

    # 检查相邻 period 之间的 overlap / gap
    prev = parsed[0]
    for cur in parsed[1:]:
        if cur["start"] < prev["end"]:
            overlap_days = (prev["end"] - cur["start"]).days
            warnings.append(
                f"Periods '{prev['label']}' and '{cur['label']}' overlap by "
                f"{overlap_days} days."
            )
        elif cur["start"] > prev["end"]:
            gap_days = (cur["start"] - prev["end"]).days
            warnings.append(
                f"There is a gap of {gap_days} days between "
                f"'{prev['label']}' and '{cur['label']}'."
            )

        # 维护“目前最晚结束时间”的那一段
        if cur["end"] > prev["end"]:
            prev = cur

    return warnings

def calculate_cgt_periods(
    buy_price: float,
    buy_date: str,
    sell_price: float,
    sell_date: str,
    ownership_percentage: float,
    capital_works_addback: float,
    periods: list,
):
    """
    periods: list of dicts like:
      {
        "label": "main",
        "start": "2012-08-01",
        "end":   "2017-06-01",
        "taxable_factor": 0.0  # 0=主居所, 1=全出租, 0.5=Airbnb 50%
      }
    """
    d_buy = parse_date(buy_date)
    d_sell = parse_date(sell_date)

    if d_sell <= d_buy:
        raise ValueError("Sell date must be after buy date.")

    holding_days = (d_sell - d_buy).days

    adjusted_cost_base = buy_price + capital_works_addback
    raw_gain = sell_price - adjusted_cost_base
    owner_gain = raw_gain * ownership_percentage

    taxable_days = 0.0
    exempt_days = 0.0
    period_details = []

    for p in periods:
        p_start = parse_date(p["start"])
        p_end = parse_date(p["end"])
        tf = float(p["taxable_factor"])  # 0~1

        overlap = days_overlap(d_buy, d_sell, p_start, p_end)
        period_taxable = overlap * tf
        period_exempt = overlap * (1 - tf)

        taxable_days += period_taxable
        exempt_days += period_exempt

        period_details.append({
            "label": p["label"],
            "start": p["start"],
            "end": p["end"],
            "overlap_days": overlap,
            "taxable_factor": tf,
            "taxable_days": period_taxable,
            "exempt_days": period_exempt,
        })

    total_covered = taxable_days + exempt_days
    uncovered_days = holding_days - total_covered  # >0 空档, <0 说明有重叠导致重复计算

    if holding_days > 0:
        taxable_fraction = taxable_days / holding_days
    else:
        taxable_fraction = 0.0
    exempt_fraction = 1 - taxable_fraction

    taxable_gain_before_discount = owner_gain * taxable_fraction
    discount_rate = 0.5 if holding_days >= 365 else 0.0
    discounted_gain = taxable_gain_before_discount * (1 - discount_rate)

    return {
        "Holding days": holding_days,
        "Taxable days": taxable_days,
        "Exempt days": exempt_days,
        "Uncovered days": uncovered_days,
        "Taxable fraction": round(taxable_fraction, 4),
        "Exempt fraction": round(exempt_fraction, 4),
        "Original cost base": buy_price,
        "Capital works add-back": capital_works_addback,
        "Adjusted cost base": adjusted_cost_base,
        "Sell price": sell_price,
        "Raw capital gain": raw_gain,
        "Ownership adjusted gain": owner_gain,
        "Taxable gain before discount": taxable_gain_before_discount,
        "Discount rate": discount_rate,
        "Final taxable gain": discounted_gain,
        "Period breakdown": period_details,
    }

if __name__ == "__main__":
    print("=== CGT Calculator v4.1 (Multi-period + validation) ===")
    print("Dates can be YYYY-MM-DD or DD/MM/YYYY\n")

    buy_price = float(input("Buy price: "))
    buy_date = input("Buy date (YYYY-MM-DD): ")

    sell_price = float(input("Sell price: "))
    sell_date = input("Sell date (YYYY-MM-DD): ")

    ownership = float(input("Ownership percentage (0-1, default 1.0): ") or 1.0)
    capital_works = float(input("Total capital works claimed to add back (default 0): ") or 0.0)

    print("\nNow enter usage periods (main residence / rental / Airbnb etc.)")
    num_periods = int(input("Number of periods: "))

    periods = []
    for i in range(num_periods):
        print(f"\n--- Period {i+1} ---")
        label = input("Label (e.g. main, rental, airbnb): ") or f"Period {i+1}"
        start = input("Start date (YYYY-MM-DD): ")
        end = input("End date (YYYY-MM-DD): ")

        print("Usage type options:")
        print("  1 = Main residence (0% taxable)")
        print("  2 = Full rental/investment (100% taxable)")
        print("  3 = Partial use (e.g. Airbnb 50%)")

        choice = input("Choose 1 / 2 / 3: ").strip()

        if choice == "1":
            tf = 0.0
        elif choice == "2":
            tf = 1.0
        else:
            pct = float(input("Enter taxable percentage (0-100): "))
            tf = pct / 100.0

        periods.append({
            "label": label,
            "start": start,
            "end": end,
            "taxable_factor": tf,
        })

    # 先做 period 校验（日期顺序 + gap/overlap 提示）
    try:
        warnings = validate_periods(buy_date, sell_date, periods)
    except ValueError as e:
        print("\nERROR in periods:", e)
        raise

    if warnings:
        print("\n--- Period warnings ---")
        for w in warnings:
            print("•", w)
    else:
        print("\nNo obvious gaps or overlaps detected in periods.")

    # 计算 CGT
    result = calculate_cgt_periods(
        buy_price=buy_price,
        buy_date=buy_date,
        sell_price=sell_price,
        sell_date=sell_date,
        ownership_percentage=ownership,
        capital_works_addback=capital_works,
        periods=periods,
    )

    print("\n--- Period breakdown ---")
    for p in result["Period breakdown"]:
        print(
            f"{p['label']}: {p['start']} -> {p['end']}, "
            f"overlap_days={p['overlap_days']}, "
            f"taxable_factor={p['taxable_factor']}, "
            f"taxable_days={p['taxable_days']}, "
            f"exempt_days={p['exempt_days']}"
        )

    print("\n--- CGT Results ---")
    for key, val in result.items():
        if key == "Period breakdown":
            continue
        print(f"{key}: {val}")

    # 根据 uncovered_days 再给一个友好提示
    ud = result["Uncovered days"]
    if ud > 0:
        print(f"\nNote: {ud} days of the holding period are not covered by any usage period.")
    elif ud < 0:
        print(f"\nNote: Periods overlap in total by {-ud} days (double-counted days).")
