import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { Play, AlertCircle, CheckCircle, Clock } from 'lucide-react';

export function Preview() {
  const [time, setTime] = useState<string>('');

  useEffect(() => {
    setTime(new Date().toLocaleTimeString());
    const interval = setInterval(() => {
      setTime(new Date().toLocaleTimeString());
    }, 1000);
    return () => clearInterval(interval);
  }, []);
  const recentActivity = [
    {
      id: 'ELISA-023',
      action: 'Completed processing',
      time: '2 min ago',
      status: 'success',
    },
    {
      id: 'IMMU-116',
      action: 'Processing delayed',
      time: '5 min ago',
      status: 'warning',
    },
    {
      id: 'PCR-089',
      action: 'Started analysis',
      time: '8 min ago',
      status: 'processing',
    },
  ];

  const systemMetrics = [
    { label: 'Queue Size', value: '247', unit: 'samples' },
    { label: 'Processing', value: '18', unit: 'active' },
    { label: 'Completed', value: '1,453', unit: 'today' },
    { label: 'Avg Time', value: '12.4', unit: 'ms' },
  ];

  return (
    <section id="preview" className="py-24 px-4 sm:px-6 lg:px-8 bg-[#F8FAFC]">
      <div className="max-w-7xl mx-auto">
        {/* Section Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center mb-16"
        >
          <div className="inline-flex items-center space-x-2 px-4 py-2 bg-white rounded-full border border-[#E2E8F0] mb-6">
            <Play size={16} className="text-[#0EA5E9]" />
            <span className="text-sm font-medium text-[#475569]">
              System Preview
            </span>
          </div>
          <h2 className="text-4xl sm:text-5xl font-bold text-[#0F172A] mb-4">
            Real-Time System Dashboard
          </h2>
          <p className="text-lg text-[#475569] max-w-2xl mx-auto">
            Monitor your entire laboratory infrastructure from a single interface
          </p>
        </motion.div>

        {/* Main Dashboard */}
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.8 }}
          className="bg-white rounded-3xl border border-[#E2E8F0] shadow-2xl overflow-hidden"
        >
          {/* Dashboard Header */}
          <div className="bg-[#F8FAFC] border-b border-[#E2E8F0] px-8 py-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xl font-bold text-[#0F172A] mb-1">
                  System Control Center
                </h3>
                <div className="flex items-center space-x-3 text-sm text-[#64748B]">
                  <span>Last updated: {time || '---'}</span>
                </div>
              </div>
              <button className="px-4 py-2 bg-[#0EA5E9] text-white text-sm font-medium rounded-lg hover:bg-[#0284C7] transition-colors">
                Refresh
              </button>
            </div>
          </div>

          {/* Dashboard Content */}
          <div className="grid lg:grid-cols-3 gap-6 p-8">
            {/* Left Column - Metrics */}
            <div className="lg:col-span-2 space-y-6">
              {/* Quick Stats */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                {systemMetrics.map((metric, index) => (
                  <motion.div
                    key={metric.label}
                    initial={{ opacity: 0, scale: 0.9 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    transition={{ delay: index * 0.1 }}
                    className="bg-[#F8FAFC] rounded-xl p-4 border border-[#E2E8F0]"
                  >
                    <div className="text-2xl font-bold text-[#0F172A] mb-1">
                      {metric.value}
                    </div>
                    <div className="text-xs text-[#64748B]">{metric.label}</div>
                    <div className="text-xs text-[#94A3B8] mt-1">
                      {metric.unit}
                    </div>
                  </motion.div>
                ))}
              </div>

              {/* Sample Processing Table */}
              <div className="bg-[#F8FAFC] rounded-2xl border border-[#E2E8F0] overflow-hidden">
                <div className="px-6 py-4 border-b border-[#E2E8F0]">
                  <h4 className="font-semibold text-[#0F172A]">
                    Active Processing Queue
                  </h4>
                </div>
                <div className="p-6">
                  <div className="space-y-3">
                    {[
                      {
                        id: 'ELISA-023',
                        status: 'PROCESSING',
                        progress: 73,
                        color: '#0EA5E9',
                      },
                      {
                        id: 'IMMU-116',
                        status: 'VALIDATING',
                        progress: 91,
                        color: '#22C55E',
                      },
                      {
                        id: 'PCR-089',
                        status: 'QUEUED',
                        progress: 12,
                        color: '#64748B',
                      },
                    ].map((item, index) => (
                      <motion.div
                        key={item.id}
                        initial={{ opacity: 0, x: -20 }}
                        whileInView={{ opacity: 1, x: 0 }}
                        viewport={{ once: true }}
                        transition={{ delay: 0.5 + index * 0.1 }}
                        className="bg-white rounded-xl p-4 border border-[#E2E8F0]"
                      >
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center space-x-3">
                            <div className="font-mono text-sm font-semibold text-[#0F172A]">
                              {item.id}
                            </div>
                            <span
                              className="text-xs font-medium px-2 py-1 rounded"
                              style={{
                                backgroundColor: `${item.color}15`,
                                color: item.color,
                              }}
                            >
                              {item.status}
                            </span>
                          </div>
                          <span className="text-sm font-medium text-[#475569]">
                            {item.progress}%
                          </span>
                        </div>
                        <div className="h-2 bg-[#E2E8F0] rounded-full overflow-hidden">
                          <motion.div
                            initial={{ width: 0 }}
                            whileInView={{ width: `${item.progress}%` }}
                            viewport={{ once: true }}
                            transition={{
                              delay: 0.6 + index * 0.1,
                              duration: 0.8,
                            }}
                            className="h-full rounded-full"
                            style={{ backgroundColor: item.color }}
                          />
                        </div>
                      </motion.div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Right Column - Activity Feed */}
            <div className="space-y-6">
              <div className="bg-[#F8FAFC] rounded-2xl border border-[#E2E8F0] overflow-hidden">
                <div className="px-6 py-4 border-b border-[#E2E8F0]">
                  <h4 className="font-semibold text-[#0F172A]">
                    Recent Activity
                  </h4>
                </div>
                <div className="p-6 space-y-4">
                  {recentActivity.map((activity, index) => (
                    <motion.div
                      key={activity.id}
                      initial={{ opacity: 0, x: 20 }}
                      whileInView={{ opacity: 1, x: 0 }}
                      viewport={{ once: true }}
                      transition={{ delay: 0.7 + index * 0.1 }}
                      className="flex items-start space-x-3"
                    >
                      <div
                        className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                          activity.status === 'success'
                            ? 'bg-[#DCFCE7]'
                            : activity.status === 'warning'
                            ? 'bg-[#FEF3C7]'
                            : 'bg-[#DBEAFE]'
                        }`}
                      >
                        {activity.status === 'success' ? (
                          <CheckCircle size={16} className="text-[#16A34A]" />
                        ) : activity.status === 'warning' ? (
                          <AlertCircle size={16} className="text-[#D97706]" />
                        ) : (
                          <Clock size={16} className="text-[#0284C7]" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-mono text-xs font-semibold text-[#0F172A] mb-1">
                          {activity.id}
                        </div>
                        <div className="text-sm text-[#475569] mb-1">
                          {activity.action}
                        </div>
                        <div className="text-xs text-[#94A3B8]">
                          {activity.time}
                        </div>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </div>

              {/* System Health */}
              <div className="bg-gradient-to-br from-[#0EA5E9]/10 to-[#22C55E]/10 rounded-2xl p-6 border border-[#E2E8F0]">
                <h4 className="font-semibold text-[#0F172A] mb-4">
                  System Health
                </h4>
                <div className="space-y-3">
                  {[
                    { label: 'CPU Usage', value: 34, color: '#0EA5E9' },
                    { label: 'Memory', value: 58, color: '#22C55E' },
                    { label: 'Storage', value: 42, color: '#8B5CF6' },
                  ].map((item) => (
                    <div key={item.label}>
                      <div className="flex justify-between text-sm mb-2">
                        <span className="text-[#475569]">{item.label}</span>
                        <span className="font-medium text-[#0F172A]">
                          {item.value}%
                        </span>
                      </div>
                      <div className="h-1.5 bg-white/50 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${item.value}%`,
                            backgroundColor: item.color,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
