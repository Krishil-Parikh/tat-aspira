import { motion } from 'motion/react';
import {
  Zap,
  Shield,
  GitBranch,
  BarChart3,
  Lock,
  Workflow,
  Clock,
  Terminal,
} from 'lucide-react';

export function Features() {
  const features = [
    {
      icon: Zap,
      title: 'Low-Latency Processing',
      description:
        'Sub-15ms average response time with edge caching and optimized query execution',
      color: '#0EA5E9',
      technical: 'Redis cache • Query optimization',
    },
    {
      icon: Shield,
      title: 'Enterprise Security',
      description:
        'End-to-end encryption, role-based access control, and comprehensive audit logging',
      color: '#22C55E',
      technical: 'AES-256 • RBAC • SOC 2',
    },
    {
      icon: GitBranch,
      title: 'Async Pipeline',
      description:
        'Event-driven architecture with automatic retries and dead letter handling',
      color: '#8B5CF6',
      technical: 'Message queue • Event sourcing',
    },
    {
      icon: BarChart3,
      title: 'Real-Time Analytics',
      description:
        'Live dashboards with sub-second data updates and custom metrics tracking',
      color: '#F59E0B',
      technical: 'WebSocket • Stream processing',
    },
    {
      icon: Lock,
      title: 'Compliance Ready',
      description:
        'HIPAA, GDPR, and ISO 9001 compliant with automated compliance reporting',
      color: '#EF4444',
      technical: 'Data residency • Audit trails',
    },
    {
      icon: Workflow,
      title: 'Workflow Automation',
      description:
        'Configurable automation rules with conditional logic and alerting system',
      color: '#06B6D4',
      technical: 'Rule engine • Webhooks',
    },
    {
      icon: Clock,
      title: 'Version Control',
      description:
        'Full data versioning with point-in-time recovery and rollback capabilities',
      color: '#84CC16',
      technical: 'Immutable logs • Time travel',
    },
    {
      icon: Terminal,
      title: 'Developer API',
      description:
        'RESTful and GraphQL APIs with comprehensive SDK support and documentation',
      color: '#F97316',
      technical: 'REST • GraphQL • SDKs',
    },
  ];

  return (
    <section id="features" className="py-24 px-4 sm:px-6 lg:px-8 bg-white">
      <div className="max-w-7xl mx-auto">
        {/* Section Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center mb-20"
        >
          <div className="inline-flex items-center space-x-2 px-4 py-2 bg-[#F1F5F9] rounded-full border border-[#E2E8F0] mb-6">
            <Terminal size={16} className="text-[#0EA5E9]" />
            <span className="text-sm font-medium text-[#475569]">
              Engineering Features
            </span>
          </div>
          <h2 className="text-4xl sm:text-5xl font-bold text-[#0F172A] mb-4">
            Built for Production
          </h2>
          <p className="text-lg text-[#475569] max-w-2xl mx-auto">
            Enterprise-grade features engineered for mission-critical laboratory operations
          </p>
        </motion.div>

        {/* Features Grid */}
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map((feature, index) => (
            <motion.div
              key={feature.title}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: index * 0.05, duration: 0.6 }}
              whileHover={{ y: -8 }}
              className="relative group"
            >
              <div className="h-full bg-[#F8FAFC] rounded-2xl p-6 border border-[#E2E8F0] hover:border-[#CBD5E1] transition-all flex flex-col">
                {/* Icon */}
                <div
                  className="w-12 h-12 rounded-xl flex items-center justify-center mb-4 transition-transform group-hover:scale-110"
                  style={{ backgroundColor: `${feature.color}15` }}
                >
                  <feature.icon size={24} style={{ color: feature.color }} />
                </div>

                {/* Content */}
                <div className="flex-1 flex flex-col space-y-3">
                  <h3 className="text-lg font-bold text-[#0F172A]">
                    {feature.title}
                  </h3>
                  <p className="text-sm text-[#475569] leading-relaxed">
                    {feature.description}
                  </p>

                  {/* Technical Badge */}
                  <div className="pt-3 border-t border-[#E2E8F0] mt-auto">
                    <div className="inline-flex items-center space-x-2 px-3 py-1.5 bg-white rounded-lg border border-[#E2E8F0]">
                      <div
                        className="w-1.5 h-1.5 rounded-full"
                        style={{ backgroundColor: feature.color }}
                      />
                      <span className="text-xs font-mono text-[#64748B]">
                        {feature.technical}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Bottom Accent */}
                <div
                  className="absolute bottom-0 left-0 right-0 h-1 rounded-b-2xl opacity-0 group-hover:opacity-100 transition-opacity"
                  style={{ backgroundColor: feature.color }}
                />
              </div>
            </motion.div>
          ))}
        </div>

        {/* Bottom CTA */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.4, duration: 0.6 }}
          className="mt-16 text-center"
        >
          <div className="bg-gradient-to-r from-[#0EA5E9]/10 via-[#22C55E]/10 to-[#8B5CF6]/10 rounded-2xl p-12 border border-[#E2E8F0]">
            <h3 className="text-2xl font-bold text-[#0F172A] mb-4">
              Want to see the full technical specifications?
            </h3>
            <p className="text-[#475569] mb-8 max-w-2xl mx-auto">
              Explore our comprehensive documentation with API references,
              architecture diagrams, and integration guides
            </p>
            <div className="flex flex-wrap justify-center gap-4">
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="px-8 py-3 bg-[#0EA5E9] text-white font-medium rounded-xl hover:bg-[#0284C7] transition-colors shadow-lg shadow-[#0EA5E9]/20"
              >
                View Documentation
              </motion.button>
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="px-8 py-3 bg-white text-[#0F172A] font-medium rounded-xl border border-[#E2E8F0] hover:border-[#CBD5E1] transition-all"
              >
                API Reference
              </motion.button>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
