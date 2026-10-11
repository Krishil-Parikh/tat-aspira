import { motion } from 'motion/react';
import { useInView } from 'motion/react';
import { useRef, useState, useEffect } from 'react';
import { Activity, Clock, CheckCircle2, TrendingUp } from 'lucide-react';

function AnimatedNumber({ value, duration = 2000 }: { value: number; duration?: number }) {
  const [count, setCount] = useState(0);
  const nodeRef = useRef<HTMLDivElement>(null);
  const isInView = useInView(nodeRef, { once: true });

  useEffect(() => {
    if (!isInView) return;

    let startTime: number;
    let animationFrame: number;

    const animate = (currentTime: number) => {
      if (!startTime) startTime = currentTime;
      const progress = Math.min((currentTime - startTime) / duration, 1);

      setCount(Math.floor(progress * value));

      if (progress < 1) {
        animationFrame = requestAnimationFrame(animate);
      }
    };

    animationFrame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animationFrame);
  }, [isInView, value, duration]);

  return <span ref={nodeRef}>{count.toLocaleString()}</span>;
}

export function Stats() {
  const stats = [
    {
      icon: Clock,
      value: 12,
      suffix: 'ms',
      label: 'Average Latency',
      description: 'End-to-end processing time',
      color: '#0EA5E9',
    },
    {
      icon: TrendingUp,
      value: 8400,
      suffix: '/h',
      label: 'Sample Throughput',
      description: 'Processed per hour',
      color: '#22C55E',
    },
    {
      icon: CheckCircle2,
      value: 99.97,
      suffix: '%',
      label: 'Success Rate',
      description: 'System reliability',
      color: '#8B5CF6',
    },
    {
      icon: Activity,
      value: 100,
      suffix: '%',
      label: 'System Uptime',
      description: 'Last 30 days',
      color: '#F59E0B',
    },
  ];

  return (
    <section className="py-24 px-4 sm:px-6 lg:px-8 bg-white border-y border-[#E2E8F0]">
      <div className="max-w-7xl mx-auto">
        {/* Section Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center mb-16"
        >
          <div className="inline-flex items-center space-x-2 px-4 py-2 bg-[#F1F5F9] rounded-full border border-[#E2E8F0] mb-6">
            <Activity size={16} className="text-[#0EA5E9]" />
            <span className="text-sm font-medium text-[#475569]">
              Performance Metrics
            </span>
          </div>
          <h2 className="text-4xl sm:text-5xl font-bold text-[#0F172A] mb-4">
            Built for Speed & Reliability
          </h2>
          <p className="text-lg text-[#475569] max-w-2xl mx-auto">
            Production-grade infrastructure engineered for high-throughput laboratory environments
          </p>
        </motion.div>

        {/* Stats Grid */}
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {stats.map((stat, index) => (
            <motion.div
              key={stat.label}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: index * 0.1, duration: 0.6 }}
              whileHover={{ y: -8, scale: 1.02 }}
              className="relative group"
            >
              {/* Card */}
              <div className="bg-[#F8FAFC] rounded-2xl p-8 border border-[#E2E8F0] hover:border-[#CBD5E1] transition-all">
                {/* Icon */}
                <div
                  className="w-12 h-12 rounded-xl flex items-center justify-center mb-6"
                  style={{ backgroundColor: `${stat.color}15` }}
                >
                  <stat.icon size={24} style={{ color: stat.color }} />
                </div>

                {/* Value */}
                <div className="mb-3">
                  <div className="flex items-baseline space-x-1">
                    <span className="text-4xl font-bold text-[#0F172A]">
                      <AnimatedNumber value={stat.value} duration={2000} />
                    </span>
                    <span className="text-2xl font-semibold text-[#475569]">
                      {stat.suffix}
                    </span>
                  </div>
                </div>

                {/* Label */}
                <div className="space-y-1">
                  <div className="text-lg font-semibold text-[#0F172A]">
                    {stat.label}
                  </div>
                  <div className="text-sm text-[#64748B]">{stat.description}</div>
                </div>

                {/* Hover indicator */}
                <div
                  className="absolute bottom-0 left-0 right-0 h-1 rounded-b-2xl opacity-0 group-hover:opacity-100 transition-opacity"
                  style={{ backgroundColor: stat.color }}
                />
              </div>
            </motion.div>
          ))}
        </div>

        {/* Bottom Info Banner */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.4, duration: 0.6 }}
          className="mt-12 bg-gradient-to-r from-[#0EA5E9]/5 via-[#22C55E]/5 to-[#0EA5E9]/5 rounded-2xl p-8 border border-[#E2E8F0]"
        >
          <div className="grid md:grid-cols-3 gap-6 text-center">
            <div>
              <div className="text-3xl font-bold text-[#0F172A] mb-2">24/7</div>
              <div className="text-sm text-[#475569]">Continuous Monitoring</div>
            </div>
            <div className="border-x border-[#E2E8F0]">
              <div className="text-3xl font-bold text-[#0F172A] mb-2">
                &lt;15s
              </div>
              <div className="text-sm text-[#475569]">Recovery Time</div>
            </div>
            <div>
              <div className="text-3xl font-bold text-[#0F172A] mb-2">
                ISO 9001
              </div>
              <div className="text-sm text-[#475569]">Quality Certified</div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
