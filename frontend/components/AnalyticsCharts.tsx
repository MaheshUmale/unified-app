import React, { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

interface PCRData {
  timestamp: string;
  pcr: number;
  call_oi: number;
  put_oi: number;
}

interface OhlcData {
  timestamp: string;
  close: number;
}

interface Props {
  pcrData: PCRData[];
  spotData: OhlcData[];
  title: string;
}

const PCRVsSpotChart: React.FC<Props> = ({ pcrData, spotData, title }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    chartRef.current = echarts.init(containerRef.current);
    const handleResize = () => chartRef.current?.resize();
    window.addEventListener('resize', handleResize);
    return () => {
        window.removeEventListener('resize', handleResize);
        chartRef.current?.dispose();
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current) return;

    // Use actual timestamp pairs for ECharts 'time' axis
    const pcrSeriesData = pcrData.map(d => [new Date(d.timestamp).getTime(), d.pcr]);
    const spotSeriesData = spotData.map(d => [new Date(d.timestamp).getTime(), d.close]);

    const option = {
        backgroundColor: 'transparent',
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' },
            backgroundColor: '#111827',
            borderColor: '#374151',
            textStyle: { color: '#e5e7eb' },
            formatter: (params: any) => {
              let res = `<div style="font-size: 10px; color: #9ca3af; margin-bottom: 4px;">${new Date(params[0].value[0]).toLocaleTimeString()}</div>`;
              params.forEach((p: any) => {
                const color = p.color;
                const value = p.value[1];
                res += `<div style="display: flex; justify-content: space-between; gap: 20px;">
                          <span style="color: ${color}">${p.seriesName}:</span>
                          <span style="font-weight: bold; color: #fff">${typeof value === 'number' ? value.toFixed(2) : value}</span>
                        </div>`;
              });
              return res;
            }
        },
        legend: {
            data: ['PCR', 'SPOT'],
            textStyle: { color: '#9ca3af', fontSize: 10 },
            top: 0
        },
        grid: { top: 40, left: 10, right: 10, bottom: 20, containLabel: true },
        xAxis: {
            type: 'time',
            axisLine: { lineStyle: { color: '#4b5563' } },
            axisLabel: {
              color: '#9ca3af',
              fontSize: 9,
              formatter: (value: number) => {
                const date = new Date(value);
                return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
              }
            },
            splitLine: { show: false }
        },
        yAxis: [
            {
                type: 'value',
                name: 'PCR',
                position: 'left',
                scale: true,
                splitLine: { show: false },
                axisLabel: { color: '#3b82f6', fontSize: 9 }
            },
            {
                type: 'value',
                name: 'SPOT',
                position: 'right',
                scale: true,
                splitLine: { lineStyle: { color: '#1f2937' } },
                axisLabel: { color: '#9ca3af', fontSize: 9 }
            }
        ],
        series: [
            {
                name: 'PCR',
                type: 'line',
                data: pcrSeriesData,
                smooth: true,
                lineStyle: { color: '#3b82f6', width: 2 },
                itemStyle: { color: '#3b82f6' },
                symbol: 'none'
            },
            {
                name: 'SPOT',
                type: 'line',
                yAxisIndex: 1,
                data: spotSeriesData,
                smooth: true,
                lineStyle: { color: '#9ca3af', width: 1, type: 'dashed' },
                itemStyle: { color: '#9ca3af' },
                symbol: 'none'
            }
        ]
    };

    chartRef.current.setOption(option);
  }, [pcrData, spotData]);

  return <div ref={containerRef} className="w-full h-full min-h-[250px]" />;
};

export default PCRVsSpotChart;
