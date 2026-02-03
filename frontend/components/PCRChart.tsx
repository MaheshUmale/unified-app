import React, { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

interface PCRData {
    timestamp: string;
    pcr: number;
}

interface Props {
    data: PCRData[];
    title: string;
}

const PCRChart: React.FC<Props> = ({ data, title }) => {
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

        const options = {
            backgroundColor: 'transparent',
            animation: false,
            tooltip: {
                trigger: 'axis',
                backgroundColor: '#111827',
                borderColor: '#374151',
                textStyle: { color: '#e5e7eb' }
            },
            title: {
                text: `${title} : ${data[data.length - 1].pcr.toFixed(2)}`,
                left: 10,
                top: 5,
                textStyle: { color: '#3b82f6', fontSize: 13, fontWeight: 'bold' }
            },
            grid: { top: 45, left: 10, right: 60, bottom: 45, containLabel: true },
            xAxis: {
                type: 'category',
                data: data.map(d => new Date(d.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })),
                axisLine: { lineStyle: { color: '#4b5563' } },
                axisLabel: { color: '#9ca3af', fontSize: 10 }
            },
            yAxis: {
                type: 'value',
                position: 'right',
                splitLine: { lineStyle: { color: '#1f2937' } },
                axisLabel: { color: '#9ca3af', fontSize: 10 }
            },
            series: [{
                name: 'PCR',
                type: 'line',
                data: data.map(d => d.pcr),
                smooth: true,
                showSymbol: false,
                lineStyle: { color: '#3b82f6', width: 2 },
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(59, 130, 246, 0.3)' },
                        { offset: 1, color: 'rgba(59, 130, 246, 0)' }
                    ])
                }
            }]
        };

        chartRef.current.setOption(options, { notMerge: true });
    }, [data, title]);

    return <div ref={containerRef} className="w-full h-full min-h-[220px]" />;
};

export default PCRChart;
