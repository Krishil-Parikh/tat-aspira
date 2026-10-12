"use client";
import React from 'react';
import { motion } from 'motion/react';
import { LucideIcon, Plus } from 'lucide-react';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function EmptyState({ icon: Icon, title, description, actionLabel, onAction }: EmptyStateProps) {
  return (
    <motion.div 
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="flex flex-col items-center justify-center p-12 text-center bg-white rounded-3xl border border-dashed border-[#CBD5E1]"
    >
      <div className="w-20 h-20 bg-[#F1F5F9] rounded-full flex items-center justify-center text-[#94A3B8] mb-6">
        <Icon size={40} />
      </div>
      
      <h3 className="text-2xl font-bold text-[#0F172A] mb-2">{title}</h3>
      <p className="text-[#64748B] max-w-sm mb-8">{description}</p>
      
      {actionLabel && (
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={onAction}
          className="flex items-center space-x-2 px-6 py-3 bg-[#0EA5E9] text-white font-bold rounded-xl shadow-lg shadow-[#0EA5E9]/20 hover:bg-[#0284C7] transition-all"
        >
          <Plus size={20} />
          <span>{actionLabel}</span>
        </motion.button>
      )}
    </motion.div>
  );
}
