import React, { useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import { OhlcData } from '../types';

interface Props {
  data: OhlcData[];
  title: string;
  color?: string;
}

const MarketChart: React.FC<Props> = ({ data, title }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    if (!chartRef.current) {
        chartRef.current = echarts.init(containerRef.current);
    }

    const handleResize = () => chartRef.current?.resize();
    window.addEventListener('resize', handleResize);

    return () => {
        window.removeEventListener('resize', handleResize);
        chartRef.current?.dispose();
        chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current || data.length === 0) return;

    const last = data[data.length - 1];
    const isUp = last.close >= last.open;
    const dates = data.map(d => new Date(d.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}));
    const values = data.map(d => [d.open, d.close, d.low, d.high]);

    const options = {
        backgroundColor: 'transparent',
        animation: false,
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'cross' },
            backgroundColor: '#111827',
            borderColor: '#374151',
            textStyle: { color: '#e5e7eb' }
        },
        title: {
            text: `${title} : ${last.close.toFixed(2)}`,
            left: 10,
            top: 5,
            textStyle: { color: isUp ? '#22c55e' : '#ef4444', fontSize: 13, fontWeight: 'bold' }
        },
        toolbox: {
            show: true,
            right: 10,
            top: 5,
            iconStyle: { borderColor: '#4b5563' },
            feature: {
                dataZoom: { yAxisIndex: 'none', title: { zoom: 'Zoom', back: 'Restore' } },
                restore: { title: 'Reset' }
            }
        },
        grid: { top: 45, left: 10, right: 60, bottom: 45, containLabel: true },
        xAxis: {
            type: 'category',
            data: dates,
            axisLine: {lineStyle: {color: '#4b5563'}},
            axisLabel: { color: '#9ca3af', fontSize: 10 }
        },
        yAxis: {
            scale: true,
            position: 'right',
            splitLine: {lineStyle: {color: '#1f2937'}},
            axisLabel: { color: '#9ca3af', fontSize: 10 }
        },
        dataZoom: [
            {
                type: 'inside',
                // Zoom to the last 50 candles by default
                start: data.length > 50 ? 100 - (5000 / data.length) : 0,
                end: 100,
                zoomOnMouseWheel: true,
                preventDefaultMouseMove: false
            },
            {
                type: 'slider',
                show: true,
                bottom: 5,
                height: 15,
                borderColor: 'transparent',
                backgroundColor: '#1f2937',
                fillerColor: 'rgba(59, 130, 246, 0.2)',
                handleStyle: { color: '#3b82f6' },
                textStyle: { color: 'transparent' }
            }
        ],
        series: [{
            name: 'Price',
            type: 'candlestick',
            data: values,
            itemStyle: {
                color: '#22c55e',
                color0: '#ef4444',
                borderColor: '#22c55e',
                borderColor0: '#ef4444'
            }
        }]
    };

    chartRef.current.setOption(options, { notMerge: true });
  }, [data, title]);

  return <div ref={containerRef} className="w-full h-full min-h-[220px]" />;
};

export default MarketChart;