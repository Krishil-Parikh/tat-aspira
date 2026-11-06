"use client";
import React, { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { Menu } from 'lucide-react';
import { cn } from '@/components/ui/utils';
import { getSessionHint, ROLE_TITLES } from '@/app/lib/session';

interface HeaderProps {
  onMenuClick: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  const [user, setUser] = useState({ name: '', title: '' });
  useEffect(() => {
    const s = getSessionHint();
    setUser({ name: s.name, title: s.role ? ROLE_TITLES[s.role] : '' });
  }, []);
  const initials = user.name.split(/[\s@.]+/).filter(Boolean).slice(0, 2)
    .map(w => w[0]!.toUpperCase()).join('');

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

      </div>

      <div className="flex items-center gap-4">
        {/* Avatar Section */}
        <div className="flex items-center gap-3 sm:pl-2 sm:border-l border-border-ghost">
          <div className="text-right hidden lg:block">
            <p className="text-xs font-black text-foreground leading-none">{user.name}</p>
            <p className="text-[8px] font-black text-muted uppercase tracking-widest mt-1">{user.title}</p>
          </div>
          <div className="w-8 h-8 rounded-full bg-primary/10 border border-primary/20 p-0.5 overflow-hidden">
            <div className="w-full h-full rounded-full bg-primary flex items-center justify-center text-white text-[10px] font-black">
              {initials}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
