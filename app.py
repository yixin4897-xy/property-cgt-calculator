from flask import Flask, request, render_template_string
from main import calculate_cgt_periods, validate_periods

app = Flask(__name__)

# 支持的最大 period 数量
NUM_PERIODS = 10

HTML = """
<!doctype html>
<html>
<head>
    <meta charset="utf-8">
    <title>Australian Property CGT Calculator (Multi-Period)</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 960px; margin: 20px auto; }
        h1 { font-size: 22px; }
        table { border-collapse: collapse; width: 100%; margin-bottom: 15px; }
        th, td { border: 1px solid #ccc; padding: 6px 8px; font-size: 13px; }
        th { background: #f0f0f0; }
        input, select { width: 100%; box-sizing: border-box; }
        .error { color: #b00020; font-weight: bold; }
        .warning { color: #b36b00; }
        .result-box { background: #f8f8f8; padding: 10px; margin-top: 15px; }
        .small { font-size: 12px; color: #555; }
    </style>
</head>
<body>
<h1>Australian Property CGT Calculator (Multi-Period)</h1>

<form method="post">

    <h2>1. Basic details</h2>
    <table>
        <tr>
            <td>Buy price</td>
            <td><input type="number" step="0.01" name="buy_price" value="{{ form.buy_price }}"></td>
            <td>Buy date</td>
            <td><input type="text" name="buy_date" value="{{ form.buy_date }}"></td>
        </tr>
        <tr>
            <td>Sell price</td>
            <td><input type="number" step="0.01" name="sell_price" value="{{ form.sell_price }}"></td>
            <td>Sell date</td>
            <td><input type="text" name="sell_date" value="{{ form.sell_date }}"></td>
        </tr>
        <tr>
            <td>Ownership % (0–1)</td>
            <td><input type="number" step="0.01" name="ownership" value="{{ form.ownership }}"></td>
            <td>Capital works add-back</td>
            <td><input type="number" step="0.01" name="capital_works" value="{{ form.capital_works }}"></td>
        </tr>
    </table>

    <h2>2. Usage periods</h2>
    <p class="small">Leave unused rows blank.</p>

    <table>
        <tr>
            <th>#</th>
            <th>Label</th>
            <th>Start date</th>
            <th>End date</th>
            <th>Usage type</th>
            <th>Taxable %</th>
        </tr>

        {% for i in range(1, num_periods + 1) %}
        <tr>
            <td>{{ i }}</td>
            <td><input type="text" name="label{{ i }}" value="{{ form['label' ~ i] }}"></td>
            <td><input type="text" name="start{{ i }}" value="{{ form['start' ~ i] }}"></td>
            <td><input type="text" name="end{{ i }}" value="{{ form['end' ~ i] }}"></td>
            <td>
                <select name="usage{{ i }}">
                    <option value=""></option>
                    <option value="main"   {% if form['usage' ~ i] == 'main' %}selected{% endif %}>Main residence (0%)</option>
                    <option value="rental" {% if form['usage' ~ i] == 'rental' %}selected{% endif %}>Full rental (100%)</option>
                    <option value="partial" {% if form['usage' ~ i] == 'partial' %}selected{% endif %}>Partial use (e.g. Airbnb)</option>
                </select>
            </td>
            <td><input type="number" step="0.1" name="taxable_pct{{ i }}" value="{{ form['taxable_pct' ~ i] }}"></td>
        </tr>
        {% endfor %}
    </table>

    <button type="submit">Calculate CGT</button>
</form>

{% if error %}
<div class="error">{{ error }}</div>
{% endif %}

{% if warnings %}
<div class="result-box">
    <h3>Warnings</h3>
    {% for w in warnings %}
        <p class="warning">• {{ w }}</p>
    {% endfor %}
</div>
{% endif %}

{% if result %}
<div class="result-box">
    <h2>CGT Summary</h2>

    <p>Holding days: {{ result["Holding days"] }}</p>
    <p>Taxable days: {{ result["Taxable days"] }}</p>
    <p>Exempt days: {{ result["Exempt days"] }}</p>

    <p>Taxable fraction: {{ result["Taxable fraction"] }}</p>
    <p>Exempt fraction: {{ result["Exempt fraction"] }}</p>

    <p>Original cost base: {{ result["Original cost base"] }}</p>
    <p>Capital works add-back: {{ result["Capital works add-back"] }}</p>
    <p>Adjusted cost base: {{ result["Adjusted cost base"] }}</p>

    <p>Raw capital gain: {{ result["Raw capital gain"] }}</p>
    <p>Ownership adjusted gain: {{ result["Ownership adjusted gain"] }}</p>
    <p>Taxable gain before discount: {{ result["Taxable gain before discount"] }}</p>

    <p>Discount rate: {{ result["Discount rate"] }}</p>

    <h3><strong>Final taxable gain: {{ result["Final taxable gain"] }}</strong></h3>

    <h3>Breakdown by Period</h3>
    <table>
        <tr>
            <th>Label</th>
            <th>Start</th>
            <th>End</th>
            <th>Overlap days</th>
            <th>Taxable factor</th>
            <th>Taxable days</th>
            <th>Exempt days</th>
        </tr>
        {% for p in result["Period breakdown"] %}
        <tr>
            <td>{{ p.label }}</td>
            <td>{{ p.start }}</td>
            <td>{{ p.end }}</td>
            <td>{{ p.overlap_days }}</td>
            <td>{{ p.taxable_factor }}</td>
            <td>{{ p.taxable_days }}</td>
            <td>{{ p.exempt_days }}</td>
        </tr>
        {% endfor %}
    </table>
</div>
{% endif %}

</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    warnings = []
    result = None

    # 初始化表单字典
    form = {
        "buy_price": "",
        "buy_date": "",
        "sell_price": "",
        "sell_date": "",
        "ownership": "1.0",
        "capital_works": "0",
    }
    for i in range(1, NUM_PERIODS + 1):
        form[f"label{i}"] = ""
        form[f"start{i}"] = ""
        form[f"end{i}"] = ""
        form[f"usage{i}"] = ""
        form[f"taxable_pct{i}"] = ""

    if request.method == "POST":
        try:
            # 基本信息
            form["buy_price"] = request.form.get("buy_price", "")
            form["buy_date"] = request.form.get("buy_date", "")
            form["sell_price"] = request.form.get("sell_price", "")
            form["sell_date"] = request.form.get("sell_date", "")
            form["ownership"] = request.form.get("ownership", "1.0")
            form["capital_works"] = request.form.get("capital_works", "0")

            buy_price = float(form["buy_price"])
            sell_price = float(form["sell_price"])
            ownership = float(form["ownership"])
            capital_works = float(form["capital_works"])
            buy_date = form["buy_date"].strip()
            sell_date = form["sell_date"].strip()

            # 收集 periods
            periods = []
            for i in range(1, NUM_PERIODS + 1):
                label = request.form.get(f"label{i}", "").strip()
                start = request.form.get(f"start{i}", "").strip()
                end = request.form.get(f"end{i}", "").strip()
                usage = request.form.get(f"usage{i}", "").strip()
                taxable_pct = request.form.get(f"taxable_pct{i}", "").strip()

                # 存回 form，方便错误时保留用户输入
                form[f"label{i}"] = label
                form[f"start{i}"] = start
                form[f"end{i}"] = end
                form[f"usage{i}"] = usage
                form[f"taxable_pct{i}"] = taxable_pct

                # start / end 没填就跳过该行
                if not start or not end:
                    continue

                if not usage:
                    raise ValueError(f"Period {i}: usage type is required.")

                if usage == "main":
                    tf = 0.0
                elif usage == "rental":
                    tf = 1.0
                else:  # partial
                    if not taxable_pct:
                        raise ValueError(f"Period {i}: taxable % required for partial usage.")
                    tf = float(taxable_pct) / 100.0

                periods.append(
                    {
                        "label": label or f"Period {i}",
                        "start": start,
                        "end": end,
                        "taxable_factor": tf,
                    }
                )

            # 调用你的验证函数（注意参数顺序：买入日、卖出日、period 列表）
            warnings = validate_periods(buy_date, sell_date, periods)

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

        except Exception as e:
            error = str(e)

    return render_template_string(
        HTML,
        form=form,
        error=error,
        warnings=warnings,
        result=result,
        num_periods=NUM_PERIODS,
    )


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

