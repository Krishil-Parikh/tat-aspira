"use client";
import React, { useState } from 'react';
import { motion } from 'motion/react';
import { useRouter } from 'next/navigation';
import { ShieldCheck, Lock, User, ArrowRight, Activity, Database } from 'lucide-react';
import { cn } from '@/components/ui/utils';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    // Roles from PRD
    const users: Record<string, { role: string, labId?: number }> = {
      'admin@aspira.com': { role: 'admin' },
      'logistics@aspira.com': { role: 'logistics' },
      'doctor@aspira.com': { role: 'doctor' },
      // Lab Managers from Demo Init
      'ghk.manager@aspira.com': { role: 'lab', labId: 1 },
      'nm.manager@aspira.com': { role: 'lab', labId: 2 },
      'shobha.manager@aspira.com': { role: 'lab', labId: 3 },
      'kharghar.manager@aspira.com': { role: 'lab', labId: 4 },
      'chembur.manager@aspira.com': { role: 'lab', labId: 5 },
      'hoc.manager@aspira.com': { role: 'lab', labId: 6 },
      'truecare.manager@aspira.com': { role: 'lab', labId: 7 },
      'sso.manager@aspira.com': { role: 'lab', labId: 8 },
      'os.manager@aspira.com': { role: 'lab', labId: 9 },
      // Legacy test accounts
      'lab_main@aspira.com': { role: 'lab', labId: 1 },
      'lab_haem@aspira.com': { role: 'lab', labId: 2 },
      'lab_biochem@aspira.com': { role: 'lab', labId: 3 },
    };

    // Simulate authentication
    setTimeout(() => {
      const user = users[email as keyof typeof users];
      if (user && password === 'aspira123') {
        // Set auth cookies. Email is now the primary session identifier for the backend.
        document.cookie = `aspira_auth=true; path=/; max-age=86400`;
        document.cookie = `aspira_email=${email}; path=/; max-age=86400`;
        document.cookie = `aspira_role=${user.role}; path=/; max-age=86400`; // UI hint only
        if (user.labId) {
          document.cookie = `aspira_lab_id=${user.labId}; path=/; max-age=86400`; // UI hint only
        }
        router.push('/dashboard');
      } else {
        setError('Invalid credentials. Access denied by security protocol.');
        setIsLoading(false);
      }
    }, 1500);
  };

  return (
    <div className="min-h-screen bg-[#F6FAFF] flex items-center justify-center p-6 relative overflow-hidden">
      {/* Background Decor */}
      <div className="absolute top-0 left-0 w-full h-full opacity-[0.03] pointer-events-none">
        <div className="absolute inset-0" style={{ backgroundImage: 'radial-gradient(#005DAC 1px, transparent 1px)', backgroundSize: '40px 40px' }} />
      </div>

      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: "circOut" }}
        className="w-full max-w-md"
      >
        <div className="bg-white rounded-[2.5rem] shadow-[0_32px_64px_-16px_rgba(0,93,172,0.12)] border border-blue-50/50 overflow-hidden relative">
          {/* Top Bar Indicator */}
          <div className="h-1.5 w-full bg-gradient-to-r from-primary via-primary-container to-primary" />
          
          <div className="p-10 pt-12">
            <div className="flex flex-col items-center text-center mb-10">
              <motion.div 
                whileHover={{ scale: 1.05 }}
                className="w-16 h-16 bg-primary rounded-2xl flex items-center justify-center mb-6 shadow-xl shadow-primary/20"
              >
                <Database className="text-white" size={32} />
              </motion.div>
              <h1 className="text-3xl font-black text-foreground tracking-tighter leading-none mb-2">
                ASPIRA<span className="text-primary">.</span>OS
              </h1>
              <p className="text-[10px] font-black text-muted uppercase tracking-[0.3em]">
                Secure Protocol Authentication
              </p>
            </div>

            <form onSubmit={handleLogin} className="space-y-6">
              <div className="space-y-2">
                <label className="block text-[10px] font-black uppercase tracking-widest text-muted ml-1">Personnel Email</label>
                <div className="relative group">
                  <User className="absolute left-4 top-1/2 -translate-y-1/2 text-muted group-focus-within:text-primary transition-colors" size={18} />
                  <input
                    required
                    type="email"
                    placeholder="admin@aspira.com"
                    className="w-full bg-surface-low border-none rounded-2xl py-4 pl-12 pr-5 font-headline font-semibold text-foreground focus:ring-2 focus:ring-primary outline-none transition-all placeholder:text-muted/40"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="block text-[10px] font-black uppercase tracking-widest text-muted ml-1">Security Key</label>
                <div className="relative group">
                  <Lock className="absolute left-4 top-1/2 -translate-y-1/2 text-muted group-focus-within:text-primary transition-colors" size={18} />
                  <input
                    required
                    type="password"
                    placeholder="••••••••"
                    className="w-full bg-surface-low border-none rounded-2xl py-4 pl-12 pr-5 font-headline font-semibold text-foreground focus:ring-2 focus:ring-primary outline-none transition-all placeholder:text-muted/40"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </div>
              </div>

              {error && (
                <motion.div 
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="bg-error/10 border border-error/30 p-4 rounded-xl flex items-center gap-3 text-error-text"
                >
                  <ShieldCheck size={18} className="shrink-0" />
                  <span className="text-[10px] font-black uppercase tracking-wider">{error}</span>
                </motion.div>
              )}

              <button
                disabled={isLoading}
                type="submit"
                className="w-full bg-primary text-white py-4 rounded-2xl font-headline font-black text-sm uppercase tracking-widest shadow-xl shadow-primary/20 hover:shadow-primary/30 hover:-translate-y-0.5 transition-all flex items-center justify-center gap-3 disabled:opacity-50 disabled:translate-y-0"
              >
                {isLoading ? (
                  <Activity className="animate-pulse" size={20} />
                ) : (
                  <>
                    Initialize Connection
                    <ArrowRight size={18} />
                  </>
                )}
              </button>
            </form>

            <div className="mt-8 pt-8 border-t border-blue-50 text-center">
              <p className="text-[9px] font-black text-muted uppercase tracking-widest flex items-center justify-center gap-2">
                <ShieldCheck size={12} className="text-primary" />
                End-to-End Encrypted Node: 10.210.1.74
              </p>
            </div>
          </div>
        </div>
        
        <p className="text-center mt-8 text-[10px] font-bold text-muted/60 uppercase tracking-widest">
          Authorized Personnel Only. Unauthorized access is logged.
        </p>
      </motion.div>
    </div>
  );
}
