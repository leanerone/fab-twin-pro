(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var chartOK = '#15803d';
  var chartOKsoft = '#86efac';
  var chartMid = '#b45309';
  var chartBad = accent2;

  // === 图1：三阶段查询耗时演进 ===
  var timeline = echarts.init(document.getElementById('chart-timeline'), null, { renderer: 'svg' });
  timeline.setOption({
    animation: false,
    tooltip: { trigger: 'axis', appendToBody: true, axisPointer: { type: 'shadow' } },
    legend: { textStyle: { color: muted }, top: 0, itemGap: 16 },
    grid: { top: 40, bottom: 70, left: 70, right: 20 },
    xAxis: {
      type: 'category',
      data: ['最早裸奔版<br>(v2.9 起)', '现状版本<br>(v2.11.1~v2.12)', '本次优化后<br>(v2.13)'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 12, lineHeight: 18 }
    },
    yAxis: {
      type: 'log',
      logBase: 10,
      name: '查询耗时（秒，对数）',
      nameTextStyle: { color: muted, fontSize: 12 },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } },
      axisLabel: { color: muted, formatter: function(v) { return v + 's'; } }
    },
    series: [
      {
        name: 'Lot 查询',
        type: 'bar',
        data: [703, 645, 0.006],
        itemStyle: { color: function(p) { return p.dataIndex === 2 ? chartOK : p.dataIndex === 1 ? chartMid : chartBad; }, borderRadius: [4,4,0,0] },
        label: { show: true, position: 'top', fontSize: 11,
                 color: function(p) { return p.dataIndex === 2 ? chartOK : (p.dataIndex === 1 ? chartMid : chartBad); },
                 formatter: function(p) { return p.value < 1 ? p.value + 's' : p.value + 's'; } }
      },
      {
        name: 'Alarm 查询',
        type: 'bar',
        data: [680, 490, 0.007],
        itemStyle: { color: function(p) { return p.dataIndex === 2 ? chartOK : p.dataIndex === 1 ? chartMid : chartBad; }, borderRadius: [4,4,0,0] },
        label: { show: true, position: 'top', fontSize: 11,
                 color: function(p) { return p.dataIndex === 2 ? chartOK : (p.dataIndex === 1 ? chartMid : chartBad); },
                 formatter: function(p) { return p.value < 1 ? p.value + 's' : p.value + 's'; } }
      },
      {
        name: '历史翻页',
        type: 'bar',
        data: [null, 458, 0.012],
        itemStyle: { color: function(p) { return p.dataIndex === 2 ? chartOK : p.dataIndex === 1 ? chartMid : chartBad; }, borderRadius: [4,4,0,0] },
        label: { show: true, position: 'top', fontSize: 11,
                 color: function(p) { return p.dataIndex === 2 ? chartOK : (p.dataIndex === 1 ? chartMid : chartBad); },
                 formatter: function(p) { return p.value < 1 ? p.value + 's' : p.value + 's'; } }
      }
    ]
  });
  window.addEventListener('resize', function() { timeline.resize(); });

  // === 图2：加速路径覆盖关系 ===
  var path = echarts.init(document.getElementById('chart-path'), null, { renderer: 'svg' });
  path.setOption({
    animation: false,
    tooltip: { trigger: 'axis', appendToBody: true, axisPointer: { type: 'shadow' } },
    legend: { textStyle: { color: muted }, top: 0 },
    grid: { top: 40, bottom: 80, left: 90, right: 30 },
    xAxis: {
      type: 'category',
      data: ['机台状态查询<br>(tool_id + ts)', '首页今日产量<br>(tool_id + ts)', 'Lot 事件查询<br>(payload_json LIKE)', 'Alarm 详情<br>(payload_json LIKE)', '历史翻页<br>(tool_id + raw_id)'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 11, lineHeight: 16 }
    },
    yAxis: {
      type: 'category',
      data: ['缓存层', '现有索引层 (v2.11.1)', '本次物化列层 (v2.13)'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: ink, fontSize: 12, fontWeight: 600 },
      splitArea: { show: true, areaStyle: { color: [bg2, 'transparent'] } }
    },
    series: [{
      type: 'heatmap',
      data: [
        // 缓存层：所有路径都被覆盖（但有三个盲区）
        [0, 0, '✅'], [1, 0, '✅'], [2, 0, '⚠️'], [3, 0, '⚠️'], [4, 0, '⚠️'],
        // 现有索引层：只覆盖有独立列的路径
        [0, 1, '✅'], [1, 1, '✅'], [2, 1, '❌'], [3, 1, '❌'], [4, 1, '❌'],
        // 本次物化列层：全覆盖
        [0, 2, '✅'], [1, 2, '✅'], [2, 2, '✅'], [3, 2, '✅'], [4, 2, '✅']
      ],
      label: { show: true, fontSize: 16, fontWeight: 700 },
      itemStyle: { borderColor: rule, borderWidth: 1 }
    }],
    visualMap: {
      show: false,
      min: 0, max: 3,
      inRange: { color: ['#fef3c7', '#fed7aa', '#dcfce7', '#bbf7d0'] }
    }
  });
  window.addEventListener('resize', function() { path.resize(); });

  // === 图3：提速倍数柱 ===
  var gain = echarts.init(document.getElementById('chart-gain'), null, { renderer: 'svg' });
  gain.setOption({
    animation: false,
    tooltip: { trigger: 'axis', appendToBody: true, valueFormatter: function(v) { return '≈ ' + Number(v).toLocaleString() + '×'; } },
    grid: { top: 30, bottom: 60, left: 80, right: 30 },
    xAxis: {
      type: 'category',
      data: ['Lot 等值查询', 'Alarm 等值查询', '历史翻页'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 12 }
    },
    yAxis: {
      type: 'log',
      logBase: 10,
      name: '提速倍数（相对最早版，对数）',
      nameTextStyle: { color: muted, fontSize: 12 },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } },
      axisLabel: { color: muted, formatter: function(v) { return v + '×'; } }
    },
    series: [
      {
        name: '现状（索引+缓存）',
        type: 'bar',
        data: [1.1, 1.4, 1.5],
        itemStyle: { color: chartMid, borderRadius: [4,4,0,0] },
        label: { show: true, position: 'top', fontSize: 11, color: chartMid, formatter: '{c}×' }
      },
      {
        name: '本次优化后',
        type: 'bar',
        data: [117000, 97000, 38000],
        itemStyle: { color: chartOK, borderRadius: [4,4,0,0] },
        label: { show: true, position: 'top', fontSize: 12, fontWeight: 700, color: chartOK,
                 formatter: function(p) { return p.value.toLocaleString() + '×'; } }
      }
    ]
  });
  window.addEventListener('resize', function() { gain.resize(); });
})();
