import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { ArrowRight, Zap, Shield, Database } from 'lucide-react';

export function Hero() {
  const [time, setTime] = useState<string>('');

  useEffect(() => {
    setTime(new Date().toLocaleTimeString());
    const interval = setInterval(() => {
      setTime(new Date().toLocaleTimeString());
    }, 1000);
    return () => clearInterval(interval);
  }, []);
  const sampleData = [
    {
      id: 'ELISA-023',
      batch: 'B-4721',
      status: 'NORMAL',
      eta: 'Fri 6 PM',
      progress: 87,
    },
    {
      id: 'IMMU-116',
      batch: 'B-4722',
      status: 'DELAYED',
      eta: 'Sat 9 AM',
      progress: 45,
    },
    {
      id: 'PCR-089',
      batch: 'B-4723',
      status: 'NORMAL',
      eta: 'Fri 8 PM',
      progress: 92,
    },
    {
      id: 'FLOW-052',
      batch: 'B-4724',
      status: 'REJECTED',
      eta: '—',
      progress: 0,
    },
  ];

  const floatingCards = [
    {
      title: 'Processing Speed',
      value: '12ms',
      description: 'Avg latency',
      icon: Zap,
    },
    {
      title: 'System Status',
      value: '99.97%',
      description: 'Uptime',
      icon: Shield,
    },
    {
      title: 'Throughput',
      value: '8.4K/h',
      description: 'Samples/hour',
      icon: Database,
    },
  ];

  return (
    <section className="relative min-h-screen pt-32 pb-20 px-4 sm:px-6 lg:px-8 overflow-hidden">
      {/* Subtle grid background */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#E2E8F0_1px,transparent_1px),linear-gradient(to_bottom,#E2E8F0_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_80%_50%_at_50%_0%,#000_70%,transparent_110%)]" />

      <div className="max-w-7xl mx-auto relative z-10">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          {/* Left Side - Content */}
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
            className="space-y-8"
          >


            {/* Headline */}
            <div className="space-y-4">
              <motion.h1
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 }}
                className="text-5xl sm:text-6xl lg:text-7xl font-bold text-[#0F172A] leading-[1.1] tracking-tight"
              >
                Real-Time Lab
                <br />
                Processing
                <br />
                Infrastructure
              </motion.h1>
              <motion.p
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4 }}
                className="text-lg sm:text-xl text-[#475569] leading-relaxed max-w-xl"
              >
                High-throughput, low-latency lab processing with millisecond
                response times. Built for reliability at scale.
              </motion.p>
            </div>

            {/* CTAs */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5 }}
              className="flex flex-wrap gap-4"
            >
              <motion.a
                href="/dashboard/accession"
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.98 }}
                className="px-8 py-4 bg-[#0EA5E9] text-white font-medium rounded-xl hover:bg-[#0284C7] transition-all shadow-lg shadow-[#0EA5E9]/20 flex items-center space-x-2"
              >
                <span>Start Scanning</span>
                <ArrowRight size={18} />
              </motion.a>
              <motion.a
                href="/dashboard"
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.98 }}
                className="px-8 py-4 bg-white text-[#0F172A] font-medium rounded-xl border border-[#E2E8F0] hover:border-[#CBD5E1] transition-all"
              >
                View Dashboard
              </motion.a>
            </motion.div>

            {/* Quick Stats */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.6 }}
              className="grid grid-cols-3 gap-6 pt-8 border-t border-[#E2E8F0]"
            >
              <div>
                <div className="text-2xl font-bold text-[#0F172A]">12ms</div>
                <div className="text-sm text-[#64748B]">Avg Latency</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-[#0F172A]">99.97%</div>
                <div className="text-sm text-[#64748B]">Success Rate</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-[#0F172A]">8.4K/h</div>
                <div className="text-sm text-[#64748B]">Throughput</div>
              </div>
            </motion.div>
          </motion.div>

          {/* Right Side - Dashboard Preview */}
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1], delay: 0.2 }}
            className="relative"
          >
            {/* Main Dashboard Card */}
            <div className="bg-white rounded-2xl border border-[#E2E8F0] shadow-2xl overflow-hidden">
              {/* Dashboard Header */}
              <div className="px-6 py-4 border-b border-[#E2E8F0] bg-[#F8FAFC]">
                <div className="flex items-center justify-end">
                  <span className="text-xs text-[#64748B]">
                    {time || '---'}
                  </span>
                </div>
              </div>

              {/* Dashboard Table */}
              <div className="p-6">
                <div className="space-y-1">
                  {/* Table Header */}
                  <div className="grid grid-cols-5 gap-4 px-4 py-3 text-xs font-medium text-[#64748B] uppercase tracking-wider">
                    <div>Sample ID</div>
                    <div>Batch</div>
                    <div>Status</div>
                    <div>ETA</div>
                    <div>Progress</div>
                  </div>

                  {/* Table Rows */}
                  {sampleData.map((sample, index) => (
                    <motion.div
                      key={sample.id}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: 0.8 + index * 0.1 }}
                      className="grid grid-cols-5 gap-4 px-4 py-4 bg-[#F8FAFC] hover:bg-[#F1F5F9] rounded-xl transition-colors border border-transparent hover:border-[#E2E8F0]"
                    >
                      <div className="text-sm font-medium text-[#0F172A]">
                        {sample.id}
                      </div>
                      <div className="text-sm text-[#475569]">
                        {sample.batch}
                      </div>
                      <div>
                        <span
                          className={`inline-flex px-2 py-1 text-xs font-medium rounded-md ${
                            sample.status === 'NORMAL'
                              ? 'bg-[#DCFCE7] text-[#16A34A]'
                              : sample.status === 'DELAYED'
                              ? 'bg-[#FEF3C7] text-[#D97706]'
                              : 'bg-[#FEE2E2] text-[#DC2626]'
                          }`}
                        >
                          {sample.status}
                        </span>
                      </div>
                      <div className="text-sm text-[#475569]">{sample.eta}</div>
                      <div className="flex items-center space-x-2">
                        <div className="flex-1 bg-[#E2E8F0] rounded-full h-2 overflow-hidden">
                          <motion.div
                            initial={{ width: 0 }}
                            animate={{ width: `${sample.progress}%` }}
                            transition={{ delay: 1 + index * 0.1, duration: 0.8 }}
                            className={`h-full ${
                              sample.status === 'NORMAL'
                                ? 'bg-[#22C55E]'
                                : sample.status === 'DELAYED'
                                ? 'bg-[#F59E0B]'
                                : 'bg-[#EF4444]'
                            }`}
                          />
                        </div>
                        <span className="text-xs text-[#64748B] w-10">
                          {sample.progress}%
                        </span>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </div>
            </div>

            {/* Floating System Cards */}
            {floatingCards.map((card, index) => (
              <motion.div
                key={card.title}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 1.2 + index * 0.15 }}
                whileHover={{ scale: 1.05, y: -5 }}
                className={`absolute bg-white/80 backdrop-blur-xl rounded-xl border border-[#E2E8F0] p-4 shadow-xl ${
                  index === 0
                    ? 'top-8 -right-4 lg:-right-12'
                    : index === 1
                    ? 'bottom-32 -left-4 lg:-left-12'
                    : 'bottom-8 -right-4 lg:-right-12'
                }`}
              >
                <div className="flex items-center space-x-3">
                  <div className="p-2 bg-[#F1F5F9] rounded-lg">
                    <card.icon size={18} className="text-[#0EA5E9]" />
                  </div>
                  <div>
                    <div className="text-xs text-[#64748B]">{card.title}</div>
                    <div className="text-lg font-bold text-[#0F172A]">
                      {card.value}
                    </div>
                    <div className="text-xs text-[#64748B]">
                      {card.description}
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </div>
    </section>
  );
}
