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

    // Align data by timestamp (simplified for same intervals)
    const timestamps = pcrData.map(d => new Date(d.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    const pcrValues = pcrData.map(d => d.pcr);

    // For spot data, we might have more points, so we try to match them or just show both
    // In a production app, we'd interpolate or align strictly.
    const spotValues = spotData.filter((_, i) => i % 15 === 0).map(d => d.close).slice(-pcrData.length);

    const option = {
        backgroundColor: 'transparent',
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' },
            backgroundColor: '#111827',
            borderColor: '#374151',
            textStyle: { color: '#e5e7eb' }
        },
        legend: {
            data: ['PCR', 'SPOT'],
            textStyle: { color: '#9ca3af', fontSize: 10 },
            top: 0
        },
        grid: { top: 40, left: 10, right: 10, bottom: 20, containLabel: true },
        xAxis: {
            type: 'category',
            data: timestamps,
            axisLine: { lineStyle: { color: '#4b5563' } },
            axisLabel: { color: '#9ca3af', fontSize: 9 }
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
                data: pcrValues,
                smooth: true,
                lineStyle: { color: '#3b82f6', width: 2 },
                itemStyle: { color: '#3b82f6' },
                symbol: 'none'
            },
            {
                name: 'SPOT',
                type: 'line',
                yAxisIndex: 1,
                data: spotValues,
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
