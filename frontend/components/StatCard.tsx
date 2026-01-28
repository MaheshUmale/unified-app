import React from 'react';

interface Props {
  label: string;
  value: string | number;
  sub?: string;
  color?: string;
}

const StatCard: React.FC<Props> = ({ label, value, sub, color = 'text-white' }) => (
  <div className="bg-gray-900 border border-gray-800 p-3 rounded flex flex-col items-center">
    <span className="text-[10px] uppercase text-gray-500 tracking-wider">{label}</span>
    <span className={`text-xl font-bold ${color}`}>{value}</span>
    {sub && <span className="text-xs text-gray-600">{sub}</span>}
  </div>
);

export default StatCard;