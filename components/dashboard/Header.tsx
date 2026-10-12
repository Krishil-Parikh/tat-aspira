"use client";
import React from 'react';
import { motion } from 'motion/react';
import { Search, User, Bell, Clock, Info, Menu } from 'lucide-react';
import { cn } from '@/components/ui/utils';

interface HeaderProps {
  onMenuClick: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  return (
    <header className="h-[52px] w-full sticky top-0 z-30 bg-white/80 backdrop-blur-xl border-b border-border-ghost px-4 sm:px-6 flex items-center justify-between">
      <div className="flex items-center gap-4 flex-1">
        {/* Mobile Menu Button */}
        <button 
          onClick={onMenuClick}
          suppressHydrationWarning
          className="p-2 lg:hidden bg-surface-low rounded-lg text-muted hover:text-primary transition-all"
        >
          <Menu size={20} />
        </button>

        {/* Search Bar */}
        <div className="relative group max-w-sm hidden md:block">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted group-focus-within:text-primary transition-colors" />
          <input 
            type="text" 
            suppressHydrationWarning
            placeholder="Search Protocol, Sample ID, or Batch..." 
            className="w-full bg-surface-low/50 border-none rounded-lg py-1.5 pl-9 pr-4 text-xs font-bold outline-none focus:ring-2 focus:ring-primary/10 transition-all text-foreground"
          />
        </div>
      </div>

      <div className="flex items-center gap-4">
        <button 
          suppressHydrationWarning
          className="p-2 rounded-full hover:bg-surface-low transition-colors duration-200 text-muted hidden sm:flex"
        >
          <Clock size={18} />
        </button>

        {/* Avatar Section */}
        <div className="flex items-center gap-3 sm:pl-2 sm:border-l border-border-ghost">
          <div className="text-right hidden lg:block">
            <p className="text-xs font-black text-foreground leading-none">Aditya Aspira</p>
            <p className="text-[8px] font-black text-muted uppercase tracking-widest mt-1">System Controller</p>
          </div>
          <div className="w-8 h-8 rounded-full bg-primary/10 border border-primary/20 p-0.5 overflow-hidden">
            <div className="w-full h-full rounded-full bg-primary flex items-center justify-center text-white text-[10px] font-black">
              AA
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
