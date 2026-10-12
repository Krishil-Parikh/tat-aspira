"use client";
import React, { useState } from 'react';
import { Sidebar } from '@/components/dashboard/Sidebar';
import { Header } from '@/components/dashboard/Header';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Sidebar */}
      <Sidebar isOpen={isSidebarOpen} setIsOpen={setIsSidebarOpen} />
      
      {/* Main Content Area */}
      <div className="lg:pl-64 flex flex-col min-h-screen transition-all duration-300">
        <Header onMenuClick={() => setIsSidebarOpen(true)} />
        
        <main className="flex-1 p-4 sm:p-6 lg:p-10 relative">
          <div className="max-w-7xl mx-auto relative z-10">
            {children}
          </div>
          
          {/* Background Decorative Elements */}
          <div className="fixed inset-0 pointer-events-none -z-10 opacity-40 overflow-hidden lg:ml-64">
            <div className="absolute top-[-10%] right-[-5%] w-[40%] h-[40%] bg-primary/5 blur-[120px] rounded-full"></div>
            <div className="absolute bottom-[-10%] left-[-5%] w-[30%] h-[30%] bg-primary-container/5 blur-[100px] rounded-full"></div>
          </div>
        </main>
      </div>
    </div>
  );
}
