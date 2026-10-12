"use client";
import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'motion/react';
import {
  LayoutDashboard, FlaskConical, FileText, Settings, LogOut,
  ChevronRight, Plus, Database, Truck, TestTube, BookOpen,
  AlertTriangle, ClipboardList
} from 'lucide-react';
import { cn } from '@/components/ui/utils';

const allNavItems = [
  { icon: LayoutDashboard, label: 'Frontier',        href: '/dashboard',             roles: ['admin', 'lab', 'logistics', 'doctor'] },
  { icon: TestTube,        label: 'Test Tracking',    href: '/dashboard/tests',       roles: ['admin', 'lab', 'doctor'] },
  { icon: Database,        label: 'Lab Management',   href: '/dashboard/labs',        roles: ['admin'] },
  { icon: TestTube,        label: 'My Work Queue',    href: '/dashboard/lab-queue',   roles: ['lab'] },
  { icon: BookOpen,        label: 'EDOS Management',  href: '/dashboard/lab-edos',    roles: ['admin','lab'] },
  { icon: Truck,           label: 'Logistics',        href: '/dashboard/logistics',   roles: ['logistics'] },
  { icon: ClipboardList,   label: 'My Samples',       href: '/dashboard/my-samples',  roles: ['doctor'] },
  { icon: Plus,            label: 'Admit Sample',     href: '/dashboard/accession',   roles: ['admin', 'doctor'] },
  { icon: AlertTriangle,   label: 'Unassigned',       href: '/dashboard/admin',       roles: ['admin'], badge: 'admin' },
  { icon: ClipboardList,   label: 'Audit Log',        href: '/dashboard/audit',       roles: ['admin'] },
  { icon: Settings,        label: 'Admin Controls',   href: '/dashboard/admin',       roles: ['admin'] },
  { icon: FileText,        label: 'Catalog',          href: '/dashboard/catalog',     roles: ['admin'] },
];

interface SidebarProps {
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
}

export function Sidebar({ isOpen, setIsOpen }: SidebarProps) {
  const pathname = usePathname();
  const router   = useRouter();
  const [mounted, setMounted] = useState(false);
  const [userEmail, setUserEmail] = useState('');
  const [userRole, setUserRole]   = useState('admin');

  useEffect(() => {
    setMounted(true);
    const cookies = document.cookie.split('; ');
    const role = cookies.find(c => c.startsWith('aspira_role='))?.split('=')[1] || 'admin';
    setUserRole(role.toLowerCase());
    setUserEmail(`${role.toLowerCase()}@aspira.com`);
  }, []);

  const handleLogout = () => {
    document.cookie = "aspira_auth=; path=/; expires=Thu, 01 Jan 1970 00:00:01 GMT";
    document.cookie = "aspira_role=; path=/; expires=Thu, 01 Jan 1970 00:00:01 GMT";
    router.push('/login');
  };

  // Filter by role and deduplicate hrefs (admin controls appears once)
  const seenHrefs = new Set<string>();
  const filteredNavItems = allNavItems.filter(item => {
    if (!item.roles.includes(userRole)) return false;
    if (seenHrefs.has(item.href)) return false;
    seenHrefs.add(item.href);
    return true;
  });

  const ROLE_COLORS: Record<string, string> = {
    admin:     'bg-red-500/10 text-red-500',
    lab:       'bg-primary/10 text-primary',
    logistics: 'bg-amber-500/10 text-amber-500',
    doctor:    'bg-success/10 text-success-text',
  };

  const SidebarContent = () => (
    <div className="flex flex-col h-full">
      {/* Brand */}
      <div className="p-8 pb-6 flex items-center space-x-4">
        <div className="w-10 h-10 bg-primary rounded-xl flex items-center justify-center shrink-0 shadow-lg shadow-primary/20">
          <Database size={20} className="text-white" />
        </div>
        <div className="flex flex-col">
          <span className="font-headline font-black text-foreground tracking-tighter text-xl leading-none">ASPIRA</span>
          <span className="text-[10px] font-black text-muted uppercase tracking-[0.2em] mt-1">Lab Ops</span>
        </div>
      </div>

      {/* Role badge */}
      <div className="px-8 pb-5">
        <span className={cn("inline-flex items-center px-3 py-1 rounded-full text-[9px] font-black uppercase tracking-widest", ROLE_COLORS[userRole] || 'bg-surface-high text-muted')}>
          {userRole === 'admin' ? '⚙ Admin' :
           userRole === 'lab' ? '🔬 Lab User' :
           userRole === 'logistics' ? '🚚 Logistics' :
           '👨‍⚕️ Doctor'}
        </span>
      </div>

      <div className="px-8 pb-3">
        <p className="text-[10px] font-black text-muted/40 uppercase tracking-[0.3em]">Navigation</p>
      </div>

      <nav className="flex-1 px-4 space-y-1 overflow-y-auto">
        {filteredNavItems.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + '/');
          return (
            <Link key={item.label} href={item.href} onClick={() => setIsOpen(false)}>
              <motion.div
                whileHover={{ x: 4 }}
                className={cn(
                  "flex items-center space-x-3 p-3.5 rounded-2xl transition-all group relative",
                  isActive
                    ? "bg-primary text-white shadow-xl shadow-primary/20"
                    : "text-muted hover:bg-surface-high hover:text-foreground"
                )}
              >
                <item.icon size={18} className={cn("shrink-0", isActive ? "text-white" : "text-muted group-hover:text-primary")} />
                <span className="font-headline font-bold text-sm">{item.label}</span>
                {isActive && (
                  <motion.div layoutId="active-indicator" className="absolute right-3 w-1.5 h-1.5 bg-white rounded-full" />
                )}
                {!isActive && (
                  <ChevronRight size={14} className="ml-auto opacity-0 group-hover:opacity-40 transition-opacity" />
                )}
              </motion.div>
            </Link>
          );
        })}
      </nav>

      {/* User card */}
      <div className="p-4 mt-auto">
        <div className="bg-surface-high/50 p-4 rounded-3xl">
          <div className="flex items-center space-x-3 mb-3">
            <div className={cn("w-8 h-8 rounded-full flex items-center justify-center font-bold text-[10px]", ROLE_COLORS[userRole] || 'bg-surface-high text-muted')}>
              {userRole.substring(0, 2).toUpperCase()}
            </div>
            <div>
              <p className="text-[10px] font-black leading-none">{userEmail}</p>
              <p className="text-[8px] font-bold text-muted uppercase mt-0.5 capitalize">{userRole}</p>
            </div>
          </div>
          <button
            suppressHydrationWarning
            onClick={handleLogout}
            className="w-full flex items-center justify-center space-x-2 p-2.5 text-error-text bg-error/10 hover:bg-error/20 rounded-xl transition-all text-[10px] font-black uppercase tracking-widest"
          >
            <LogOut size={14} />
            <span>Terminate Session</span>
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <>
      <aside className="fixed inset-y-0 left-0 w-64 bg-surface-low border-r border-border-ghost hidden lg:flex flex-col z-40">
        {mounted ? <SidebarContent /> : <div className="p-8"><div className="w-8 h-8 bg-surface-high animate-pulse rounded-lg" /></div>}
      </aside>

      <AnimatePresence>
        {isOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              onClick={() => setIsOpen(false)}
              className="fixed inset-0 bg-background/80 backdrop-blur-sm z-40 lg:hidden"
            />
            <motion.aside
              initial={{ x: -280 }} animate={{ x: 0 }} exit={{ x: -280 }}
              transition={{ type: 'spring', damping: 25, stiffness: 200 }}
              className="fixed inset-y-0 left-0 w-72 bg-surface-low border-r border-border-ghost z-50 lg:hidden shadow-2xl"
            >
              <SidebarContent />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
