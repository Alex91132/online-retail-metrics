/* Записка строится из window.DATA (scripts/export_page.py). */
(function () {
  const D = window.DATA;
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const el = (id) => document.getElementById(id);
  const nf = (x, d = 0) => x.toLocaleString("ru-RU", { minimumFractionDigits: d, maximumFractionDigits: d });
  const money = (x) => {
    const s = x < 0 ? "−" : "", a = Math.abs(x);
    if (a >= 1e6) return `${s}£${nf(a / 1e6, 2)} млн`;
    if (a >= 1e3) return `${s}£${nf(a / 1e3, 0)} тыс.`;
    return `${s}£${nf(a, 0)}`;
  };
  const pct = (x, d = 1) => {
    const a = nf(Math.abs(x) * 100, d);
    return `${Number(a.replace(",", ".")) === 0 ? "" : x < 0 ? "−" : "+"}${a} %`;
  };
  const share = (x, d = 0) => `${nf(x * 100, d)} %`;
  const svg = (w, h, body, label) => `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${label}">${body}</svg>`;
  const Y = Object.fromEntries(D.years.map((r) => [r.period, r]));
  const y1 = Y["Год 1"], y2 = Y["Год 2"], T1 = D.total["Год 1"], T2 = D.total["Год 2"];
  const step = (name) => D.bridge.find((r) => r.step === name).value;
  const bc = D.bridge_counts;

  /* ---------- KPI ---------- */
  const kpi = (title, v, d, good) => `<div class="kpi"><small>${title}</small><b>${v}</b>
    <span class="d ${good ? "up" : "down"}">${d} к году 1</span></div>`;
  const cr = D.cancel_rate;
  el("kpis").innerHTML = [
    kpi("Выручка, год 2", money(T2), pct(T2 / T1 - 1), T2 >= T1),
    kpi("Выручка клиентов с ID", money(y2.revenue), pct(y2.revenue / y1.revenue - 1), y2.revenue >= y1.revenue),
    kpi("Клиентов с ID", nf(y2.customers), pct(y2.customers / y1.customers - 1), true),
    kpi("Заказов на клиента", nf(y2.frequency, 2), pct(y2.frequency / y1.frequency - 1), false),
    kpi("Средний чек", money(y2.aov), pct(y2.aov / y1.aov - 1), true),
    kpi("Доля отмен", share(cr["Год 2"], 1), `${cr["Год 2"] > cr["Год 1"] ? "+" : "−"}${nf(Math.abs(cr["Год 2"] - cr["Год 1"]) * 100, 1)} п.п.`, cr["Год 2"] <= cr["Год 1"]),
  ].join("");

  const lostShare = -step("Ушли клиенты") / y1.revenue;
  el("verdict").innerHTML = `
    <p><b>Вывод.</b> Общая выручка выросла на ${pct(T2 / T1 - 1).replace("+", "")}, но выручка клиентов с ID упала на
      ${pct(y2.revenue / y1.revenue - 1).replace("−", "")}: рост дали заказы без ID клиента (${money(step("Продажи без ID клиента"))})
      и новые клиенты. Из ${nf(bc.y1)} клиентов года 1 ушёл ${nf(bc.lost)} — с ними ${money(-step("Ушли клиенты"))}
      (${share(lostShare)} их выручки), а оставшиеся ${nf(bc.retained)} купили на ${money(-step("Оставшиеся купили меньше"))} меньше.</p>
    <p>Главный фактор — <b>частота покупок</b>: ${pct(y2.frequency / y1.frequency - 1)} заказов на клиента, это
      ${money(D.factors.find((f) => f.factor === "Частота покупок").contribution)} выручки. Новые клиенты удерживаются
      не хуже прежнего; теряем частоту в старой базе. <b>Первое действие</b> — проверить, не прячутся ли постоянные клиенты
      в заказах без ID; затем — реактивация 737 клиентов «Нельзя потерять» и «Под угрозой» с A/B-тестом.</p>`;

  /* ---------- мост ---------- */
  (function () {
    const rows = D.bridge, W = 760, H = 330, L = 20, R = 20, top = 44, bot = 70;
    const bw = (W - L - R) / rows.length;
    let run = 0;
    const bars = rows.map((r) => {
      if (r.kind === "total") { run = r.value; return { ...r, a: 0, b: r.value }; }
      const a = run; run += r.value; return { ...r, a, b: run };
    });
    const lo = 7.5e6, hi = Math.max(...bars.map((b) => Math.max(b.a, b.b))) * 1.04;
    const y = (v) => top + (hi - v) / (hi - lo) * (H - top - bot);
    let b = `<text x="${L}" y="20" font-size="14" font-weight="600">Ушедшие клиенты стоили ${money(-step("Ушли клиенты"))}, новые перекрыли это с запасом</text>`;
    b += `<text x="${L}" y="36" class="muted" font-size="11.5">Ось обрезана на £7,5 млн, чтобы были видны шаги; итоги — серые, рост — зелёный, падение — красный</text>`;
    bars.forEach((r, i) => {
      const x = L + i * bw + bw * 0.15, w = bw * 0.7;
      const c = r.kind === "total" ? css("--quiet") : r.value >= 0 ? css("--good") : css("--bad");
      const y0 = y(Math.max(r.a, r.b)), y1_ = y(r.kind === "total" ? lo : Math.min(r.a, r.b));
      b += `<rect x="${x}" y="${y0}" width="${w}" height="${Math.max(1, y1_ - y0)}" rx="3" fill="${c}" opacity="${r.kind === "total" ? 1 : 0.75}"><title>${r.step}: ${money(r.value)}</title></rect>`;
      b += `<text x="${x + w / 2}" y="${y0 - 6}" text-anchor="middle" font-weight="${r.kind === "total" ? 600 : 400}">${r.kind === "total" ? money(r.value) : (r.value > 0 ? "+" : "") + money(r.value)}</text>`;
      if (i < bars.length - 1) b += `<line x1="${x + w}" x2="${x + bw}" y1="${y(r.b)}" y2="${y(r.b)}" stroke="${css("--quiet")}" stroke-dasharray="3 3"/>`;
      const words = r.step.split(" "), mid = Math.ceil(words.length / 2);
      b += `<text x="${x + w / 2}" y="${H - bot + 18}" text-anchor="middle" class="muted" font-size="11.5">${words.slice(0, mid).join(" ")}</text>`;
      b += `<text x="${x + w / 2}" y="${H - bot + 33}" text-anchor="middle" class="muted" font-size="11.5">${words.slice(mid).join(" ")}</text>`;
    });
    el("bridge").innerHTML = svg(W, H, b, "Мост выручки год к году") +
      `<p class="note">Клиент «ушёл», если покупал в году 1 и ни разу в году 2. «Без ID» — заказы, где покупатель не определён:
       их стало меньше (1 551 → 1 331), но средний такой заказ вырос с £686 до £1 057.</p>`;
  })();

  /* ---------- факторы ---------- */
  (function () {
    const f = D.factors, W = 760, H = 200, L = 190, R = 150, top = 40;
    const mx = Math.max(...f.map((r) => Math.abs(r.contribution))) * 1.15;
    const x0 = L + (W - L - R) / 2, x = (v) => x0 + v / mx * (W - L - R) / 2;
    let b = `<text x="20" y="20" font-size="14" font-weight="600">Частота покупок упала на 4,3 % — это ${money(f[1].contribution)}</text>`;
    b += `<line x1="${x0}" x2="${x0}" y1="${top - 6}" y2="${H - 10}" stroke="${css("--quiet")}"/>`;
    f.forEach((r, i) => {
      const yy = top + i * 50, c = r.contribution >= 0 ? css("--good") : css("--bad");
      b += `<text x="${L - 12}" y="${yy + 15}" text-anchor="end">${r.factor}</text>`;
      b += `<text x="${L - 12}" y="${yy + 31}" text-anchor="end" class="muted" font-size="11.5">${nf(r.before, r.before > 100 ? 0 : 2)} → ${nf(r.after, r.after > 100 ? 0 : 2)} (${pct(r.change_pct)})</text>`;
      b += `<rect x="${Math.min(x0, x(r.contribution))}" y="${yy + 4}" width="${Math.abs(x(r.contribution) - x0)}" height="26" rx="3" fill="${c}" opacity="0.75"><title>${r.factor}: ${money(r.contribution)}</title></rect>`;
      // подпись всегда справа от нулевой линии: слева от отрицательного столбика стоит название фактора
      const tx = r.contribution >= 0 ? x(r.contribution) + 8 : x0 + 8;
      b += `<text x="${tx}" y="${yy + 22}" font-weight="600">${(r.contribution > 0 ? "+" : "") + money(r.contribution)}</text>`;
    });
    el("factors").innerHTML = svg(W, H, b, "Вклад факторов в изменение выручки") +
      `<p class="note">Итого ${money(y2.revenue - y1.revenue)}: клиентов стало больше, чек чуть вырос, но каждый клиент в среднем
       сделал 4,1 заказа вместо 4,3. У клиентов, покупавших в оба года, заказов стало на 8 % меньше.</p>`;
  })();

  /* ---------- сезонность ---------- */
  (function () {
    const order = [12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], mn = ["дек", "янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя"];
    const W = 380, H = 250, L = 46, R = 14, top = 44, bot = 30;
    const get = (p) => order.map((m) => D.monthly.find((r) => r.period === p && r.m === m).revenue);
    const s1 = get("Год 1"), s2 = get("Год 2"), hi = 1.5e6;
    const x = (i) => L + i * (W - L - R) / 11, y = (v) => top + (hi - v) / hi * (H - top - bot);
    let b = `<text x="0" y="18" font-size="14" font-weight="600">Ноябрь — почти втрое выше февраля</text>`;
    b += `<text x="0" y="34" class="muted" font-size="11.5">Выручка по месяцам, £ млн</text>`;
    [0, 0.5e6, 1e6, 1.5e6].forEach((v) => { b += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="${css("--grid")}"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end" class="muted" font-size="11">${nf(v / 1e6, 1)}</text>`; });
    mn.forEach((m, i) => { if (i % 2 === 0) b += `<text x="${x(i)}" y="${H - 10}" text-anchor="middle" class="muted" font-size="11">${m}</text>`; });
    const line = (s, c, w) => `<polyline points="${s.map((v, i) => `${x(i)},${y(v)}`).join(" ")}" fill="none" stroke="${c}" stroke-width="${w}"/>`;
    b += line(s1, css("--quiet"), 2) + line(s2, css("--accent"), 2.5);
    b += `<text x="${x(11) - 4}" y="${y(s2[11]) - 8}" text-anchor="end" fill="${css("--accent")}" font-size="11.5" font-weight="600">год 2</text>`;
    b += `<text x="${x(4)}" y="${y(s1[4]) - 10}" text-anchor="middle" class="muted" font-size="11.5">год 1</text>`;
    el("seasonal").innerHTML = svg(W, H, b, "Сезонность выручки");
  })();

  /* ---------- регионы ---------- */
  (function () {
    const regs = ["Великобритания", "Европа", "Остальной мир"], W = 380, H = 250, L = 112, R = 70, top = 46;
    const mx = Math.max(...regs.map((r) => D.region[r].y2, ...regs.map((r) => D.region[r].y1)));
    const x = (v) => L + v / mx * (W - L - R);
    let b = `<text x="0" y="18" font-size="14" font-weight="600">Великобритания — на месте, рост за её пределами</text>`;
    b += `<text x="0" y="34" class="muted" font-size="11.5">серое — год 1, синее — год 2</text>`;
    regs.forEach((r, i) => {
      const v = D.region[r], yy = top + i * 64;
      b += `<text x="${L - 10}" y="${yy + 22}" text-anchor="end">${r}</text>`;
      b += `<rect x="${L}" y="${yy + 4}" width="${x(v.y1) - L}" height="14" rx="2" fill="${css("--quiet")}"/>`;
      b += `<rect x="${L}" y="${yy + 22}" width="${Math.max(2, x(v.y2) - L)}" height="14" rx="2" fill="${css("--accent")}"/>`;
      b += `<text x="${Math.max(x(v.y1), x(v.y2)) + 6}" y="${yy + 26}" font-weight="600">${pct(v.y2 / v.y1 - 1, 0)}</text>`;
      b += `<text x="${Math.max(x(v.y1), x(v.y2)) + 6}" y="${yy + 41}" class="muted" font-size="11">${money(v.y2)}</text>`;
    });
    el("regions").innerHTML = svg(W, H, b, "Выручка по регионам") +
      `<p class="note">Почти весь рост «остального мира» — Австралия: £29 тыс. → £137 тыс.</p>`;
  })();

  /* ---------- когорты ---------- */
  (function () {
    const cs = [...new Set(D.cohorts.map((c) => c.cohort))];
    const at = (c, n) => D.cohorts.find((r) => r.cohort === c && r.n === n);
    const months = ["", "янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
    const label = (c) => `${months[+c.slice(5)]} ${c.slice(2, 4)}`;
    let h = `<p style="margin:0 0 4px;font-weight:600">Через месяц возвращается каждый пятый новый клиент — и во втором году не реже</p>
      <p class="note" style="margin:0 0 10px">Доля клиентов когорты, купивших через N месяцев после первой покупки. Первая когорта (дек 2009) —
      вся накопленная база до начала данных, поэтому её нет.</p><table><thead><tr><th>Когорта</th><th>Клиентов</th>`;
    for (let n = 1; n <= 12; n++) h += `<th>${n}</th>`;
    h += `</tr></thead><tbody>`;
    cs.forEach((c) => {
      h += `<tr><td>${label(c)}</td><td>${at(c, 0).size}</td>`;
      for (let n = 1; n <= 12; n++) {
        const r = at(c, n);
        h += r ? `<td style="background:rgba(37,99,235,${Math.min(0.85, r.retention * 2.2).toFixed(2)});color:${r.retention > 0.25 ? "#fff" : "inherit"}">${nf(r.retention * 100)}</td>` : `<td></td>`;
      }
      h += `</tr>`;
    });
    el("cohorts").innerHTML = h + `</tbody></table><p class="note">Среднее удержание через месяц: когорты янв–авг 2010 — 19 %,
      янв–авг 2011 — 21 %. Новые клиенты приходят и возвращаются как раньше; выручку теряем на старой базе.</p>`;
  })();

  /* ---------- сегменты ---------- */
  (function () {
    const s = D.segments, W = 760, H = 60 + s.length * 40, L = 150, R = 80, top = 50;
    const x = (v) => L + v * (W - L - R) / 0.8;
    let b = `<text x="20" y="20" font-size="14" font-weight="600">27 % клиентов («Чемпионы») дают 74 % выручки</text>`;
    b += `<text x="20" y="38" class="muted" font-size="11.5">RFM-сегменты на 10.12.2011: серое — доля клиентов, синее — доля выручки за всё время</text>`;
    s.forEach((r, i) => {
      const yy = top + i * 40;
      b += `<text x="${L - 10}" y="${yy + 20}" text-anchor="end">${r.segment}</text>`;
      b += `<rect x="${L}" y="${yy + 4}" width="${x(r.share_customers) - L}" height="13" rx="2" fill="${css("--quiet")}"/>`;
      b += `<rect x="${L}" y="${yy + 19}" width="${Math.max(2, x(r.share_revenue) - L)}" height="13" rx="2" fill="${css("--accent")}"/>`;
      b += `<text x="${x(r.share_customers) + 6}" y="${yy + 15}" class="muted" font-size="11">${share(r.share_customers)} · ${nf(r.customers)} кл.</text>`;
      b += `<text x="${x(r.share_revenue) + 6}" y="${yy + 30}" font-size="11" font-weight="600">${share(r.share_revenue)}</text>`;
    });
    el("segments").innerHTML = svg(W, H, b, "RFM-сегменты") +
      `<p class="note">«Нельзя потерять» — 303 клиента, медиана — 6 заказов, но последний был около 317 дней назад;
       «Под угрозой» — ещё 434. В году 1 эти 737 клиентов принесли £1,16 млн, в году 2 — £0,28 млн.</p>`;
  })();

  /* ---------- рекомендации и ограничения ---------- */
  el("recs").innerHTML = `
    <li><b>Сначала — разобраться с заказами без ID.</b> Их доля в выручке выросла с 12 % до 15 %, средний такой заказ —
      £1 057 против £467 у клиентов с ID. Если это постоянные клиенты, оформившие заказ без входа в аккаунт, то часть
      «падения частоты» — артефакт учёта. Проверка с командой, которая ведёт учёт заказов, дешевле любой кампании.</li>
    <li><b>Реактивировать 737 клиентов</b> «Нельзя потерять» и «Под угрозой» (список — в витрине
      <code>customers.csv</code> и на дашборде). Это бывшие частые покупатели: в году 1 — £1,16 млн, в году 2 — £0,28 млн.
      Эффект проверить A/B-тестом с контрольной группой — без неё вернувшихся сами по себе припишем кампании
      (как это делается — <a href="https://github.com/Alex91132/ab-case-email-campaign">A/B-кейс</a>).</li>
    <li><b>Следить за частотой, а не только за выручкой.</b> Выручка выросла, и падение частоты на 4 % на месячном
      дашборде не видно. В отчётность — заказы на клиента у «Чемпионов» по месяцам с порогом тревоги.</li>
    <li><b>Австралию и Европу — в отдельные цели.</b> Это единственные растущие регионы: Великобритания (85 % выручки)
      не изменилась.</li>`;
  el("limits").innerHTML = `<p style="margin:0">Нет себестоимости и маржи — выводы о выручке, не о прибыли. Сравнение
    «крупные клиенты стали покупать меньше» по группам выручки года 1 частично объясняется возвратом к среднему, поэтому
    в выводе — падение числа заказов у всех оставшихся (−8 %), а не группы. Данные заканчиваются 9.12.2011; год 1
    начинается с уже существующей базой — «новые» в нём частично старые клиенты, впервые попавшие в данные: поэтому
    когорты начала 2010 года крупнее, мост считается только для года 2, а «новые» года 2 — это клиенты, которых
    не было в данных за предыдущие 12 месяцев.</p>`;

  if (D.datalens) el("dl-link").innerHTML = `<a href="${D.datalens}"><b>Интерактивный дашборд в DataLens</b></a>`;
})();
