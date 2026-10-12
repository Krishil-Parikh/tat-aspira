import { motion } from 'motion/react';
import { ScanLine, Cpu, Database, ArrowRight } from 'lucide-react';

export function HowItWorks() {
  const steps = [
    {
      number: '01',
      title: 'Scan',
      description: 'Automated sample intake with barcode verification and metadata capture',
      icon: ScanLine,
      color: '#0EA5E9',
      details: [
        'QR/Barcode recognition',
        'Automated logging',
        'Batch assignment',
      ],
    },
    {
      number: '02',
      title: 'Process',
      description: 'Real-time analysis pipeline with parallel processing and quality control',
      icon: Cpu,
      color: '#22C55E',
      details: [
        'Parallel execution',
        'ML-based validation',
        'Error detection',
      ],
    },
    {
      number: '03',
      title: 'Store',
      description: 'Encrypted data storage with full audit trails and compliance reporting',
      icon: Database,
      color: '#8B5CF6',
      details: [
        'AES-256 encryption',
        'Immutable logs',
        'HIPAA compliant',
      ],
    },
  ];

  return (
    <section className="py-24 px-4 sm:px-6 lg:px-8 bg-[#F8FAFC]">
      <div className="max-w-7xl mx-auto">
        {/* Section Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="text-center mb-20"
        >
          <div className="inline-flex items-center space-x-2 px-4 py-2 bg-white rounded-full border border-[#E2E8F0] mb-6">
            <div className="w-2 h-2 bg-[#0EA5E9] rounded-full animate-pulse" />
            <span className="text-sm font-medium text-[#475569]">
              Processing Pipeline
            </span>
          </div>
          <h2 className="text-4xl sm:text-5xl font-bold text-[#0F172A] mb-4">
            How ASPIRA Works
          </h2>
          <p className="text-lg text-[#475569] max-w-2xl mx-auto">
            A streamlined three-stage pipeline designed for maximum throughput and reliability
          </p>
        </motion.div>

        {/* Steps */}
        <div className="relative">
          {/* Connection Lines - Desktop */}
          <div className="hidden lg:block absolute top-1/2 left-0 right-0 h-0.5 bg-gradient-to-r from-[#0EA5E9] via-[#22C55E] to-[#8B5CF6] opacity-20 -translate-y-1/2" />

          <div className="grid lg:grid-cols-3 gap-8 lg:gap-12">
            {steps.map((step, index) => (
              <motion.div
                key={step.number}
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: index * 0.2, duration: 0.6 }}
                className="relative"
              >
                {/* Card */}
                <div className="bg-white rounded-2xl p-8 border border-[#E2E8F0] hover:border-[#CBD5E1] transition-all group hover:shadow-xl">
                  {/* Step Number */}
                  <div className="flex items-center justify-between mb-6">
                    <span
                      className="text-7xl font-bold opacity-10"
                      style={{ color: step.color }}
                    >
                      {step.number}
                    </span>
                    <div
                      className="w-14 h-14 rounded-xl flex items-center justify-center transition-transform group-hover:scale-110"
                      style={{ backgroundColor: `${step.color}15` }}
                    >
                      <step.icon size={28} style={{ color: step.color }} />
                    </div>
                  </div>

                  {/* Content */}
                  <div className="space-y-4">
                    <h3 className="text-2xl font-bold text-[#0F172A]">
                      {step.title}
                    </h3>
                    <p className="text-[#475569] leading-relaxed">
                      {step.description}
                    </p>

                    {/* Details List */}
                    <ul className="space-y-2 pt-4 border-t border-[#E2E8F0]">
                      {step.details.map((detail, i) => (
                        <li
                          key={i}
                          className="flex items-center space-x-2 text-sm text-[#64748B]"
                        >
                          <div
                            className="w-1.5 h-1.5 rounded-full"
                            style={{ backgroundColor: step.color }}
                          />
                          <span>{detail}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* Bottom Accent */}
                  <div
                    className="absolute bottom-0 left-0 right-0 h-1 rounded-b-2xl opacity-0 group-hover:opacity-100 transition-opacity"
                    style={{ backgroundColor: step.color }}
                  />
                </div>

                {/* Arrow - Desktop Only */}
                {index < steps.length - 1 && (
                  <div className="hidden lg:flex absolute top-1/2 -right-6 -translate-y-1/2 z-10">
                    <div className="w-12 h-12 bg-white rounded-full border-2 border-[#E2E8F0] flex items-center justify-center">
                      <ArrowRight size={20} className="text-[#0EA5E9]" />
                    </div>
                  </div>
                )}

                {/* Arrow - Mobile Only */}
                {index < steps.length - 1 && (
                  <div className="lg:hidden flex justify-center py-4">
                    <div className="w-12 h-12 bg-white rounded-full border-2 border-[#E2E8F0] flex items-center justify-center rotate-90">
                      <ArrowRight size={20} className="text-[#0EA5E9]" />
                    </div>
                  </div>
                )}
              </motion.div>
            ))}
          </div>
        </div>

        {/* Technical Specs */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.6, duration: 0.6 }}
          className="mt-16 bg-white rounded-2xl p-8 border border-[#E2E8F0]"
        >
          <div className="grid md:grid-cols-4 gap-6">
            <div className="text-center">
              <div className="text-sm text-[#64748B] mb-2">Pipeline Stages</div>
              <div className="text-2xl font-bold text-[#0F172A]">3</div>
            </div>
            <div className="text-center md:border-x border-[#E2E8F0]">
              <div className="text-sm text-[#64748B] mb-2">Processing Time</div>
              <div className="text-2xl font-bold text-[#0F172A]">12ms</div>
            </div>
            <div className="text-center md:border-r border-[#E2E8F0]">
              <div className="text-sm text-[#64748B] mb-2">Parallel Jobs</div>
              <div className="text-2xl font-bold text-[#0F172A]">64</div>
            </div>
            <div className="text-center">
              <div className="text-sm text-[#64748B] mb-2">Queue Depth</div>
              <div className="text-2xl font-bold text-[#0F172A]">10K+</div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
