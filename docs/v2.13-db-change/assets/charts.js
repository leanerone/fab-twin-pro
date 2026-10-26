(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  // --- Chart: 性能对比 ---
  var perf = echarts.init(document.getElementById('chart-perf'), null, { renderer: 'svg' });
  perf.setOption({
    animation: false,
    tooltip: { trigger: 'axis', appendToBody: true, valueFormatter: function(v) { return v + ' 秒'; } },
    legend: { textStyle: { color: muted }, top: 0 },
    grid: { top: 40, bottom: 60, left: 60, right: 20 },
    xAxis: {
      type: 'category',
      data: ['按 Lot 查事件', '按 Alarm 查详情', '历史回放翻页'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 12 }
    },
    yAxis: {
      type: 'value',
      name: '查询耗时（秒，对数刻度）',
      nameTextStyle: { color: muted, fontSize: 12 },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } },
      axisLabel: { color: muted }
    },
    series: [
      {
        name: '改前 LIKE 全表扫',
        type: 'bar',
        data: [645, 490, 458],
        itemStyle: { color: accent2, borderRadius: [4, 4, 0, 0] },
        label: { show: true, position: 'top', color: accent2, formatter: '{c}s', fontSize: 12 }
      },
      {
        name: '改后 物化列+索引',
        type: 'bar',
        data: [0.006, 0.007, 0.012],
        itemStyle: { color: accent, borderRadius: [4, 4, 0, 0] },
        label: { show: true, position: 'top', color: accent, formatter: '{c}s', fontSize: 12 }
      }
    ]
  });
  window.addEventListener('resize', function() { perf.resize(); });

  // --- Chart: 提速倍数 ---
  var gain = echarts.init(document.getElementById('chart-gain'), null, { renderer: 'svg' });
  gain.setOption({
    animation: false,
    tooltip: { trigger: 'axis', appendToBody: true, valueFormatter: function(v) { return '≈ ' + v.toFixed(0) + ' 倍'; } },
    grid: { top: 30, bottom: 60, left: 60, right: 30 },
    xAxis: {
      type: 'category',
      data: ['Lot 等值查询', 'Alarm 等值查询', '历史翻页'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 12 }
    },
    yAxis: {
      type: 'log',
      logBase: 10,
      name: '提速倍数（对数）',
      nameTextStyle: { color: muted, fontSize: 12 },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } },
      axisLabel: { color: muted, formatter: function(v) { return v + '×'; } }
    },
    series: [{
      type: 'bar',
      data: [107500, 70000, 38000],
      itemStyle: { color: accent, borderRadius: [4, 4, 0, 0] },
      label: { show: true, position: 'top', color: accent, fontSize: 13, fontWeight: 700,
               formatter: function(p) { return p.value.toLocaleString() + '×'; } }
    }]
  });
  window.addEventListener('resize', function() { gain.resize(); });
})();
