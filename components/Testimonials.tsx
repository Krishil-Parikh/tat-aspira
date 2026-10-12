import { motion } from 'motion/react';
import { Quote } from 'lucide-react';

export function Testimonials() {
  const testimonials = [
    {
      quote:
        'ASPIRA reduced our processing time by 87%. The real-time monitoring has completely transformed our workflow efficiency.',
      author: 'Dr. Sarah Chen',
      role: 'Lab Director',
      organization: 'GeneTech Research',
    },
    {
      quote:
        'The reliability and uptime are exceptional. We process 50,000+ samples monthly without a single data loss incident.',
      author: 'Michael Rodriguez',
      role: 'Chief Technology Officer',
      organization: 'BioMed Analytics',
    },
    {
      quote:
        'Integration was seamless. The API documentation is comprehensive and the support team is incredibly responsive.',
      author: 'Dr. Emily Watson',
      role: 'Head of Operations',
      organization: 'Clinical Diagnostics Lab',
    },
  ];

  return (
    <section className="py-24 px-4 sm:px-6 lg:px-8 bg-white">
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
            <Quote size={16} className="text-[#0EA5E9]" />
            <span className="text-sm font-medium text-[#475569]">
              Testimonials
            </span>
          </div>
          <h2 className="text-4xl sm:text-5xl font-bold text-[#0F172A] mb-4">
            Trusted by Leading Labs
          </h2>
          <p className="text-lg text-[#475569] max-w-2xl mx-auto">
            See how organizations are achieving faster, more reliable results with ASPIRA
          </p>
        </motion.div>

        {/* Testimonials Grid */}
        <div className="grid md:grid-cols-3 gap-8">
          {testimonials.map((testimonial, index) => (
            <motion.div
              key={testimonial.author}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: index * 0.15, duration: 0.6 }}
              whileHover={{ y: -8 }}
              className="bg-[#F8FAFC] rounded-2xl p-8 border border-[#E2E8F0] hover:border-[#CBD5E1] transition-all"
            >
              {/* Quote Icon */}
              <div className="w-12 h-12 bg-[#0EA5E9]/10 rounded-xl flex items-center justify-center mb-6">
                <Quote size={24} className="text-[#0EA5E9]" />
              </div>

              {/* Quote Text */}
              <p className="text-[#475569] leading-relaxed mb-6">
                "{testimonial.quote}"
              </p>

              {/* Author Info */}
              <div className="pt-6 border-t border-[#E2E8F0]">
                <div className="font-semibold text-[#0F172A] mb-1">
                  {testimonial.author}
                </div>
                <div className="text-sm text-[#64748B]">{testimonial.role}</div>
                <div className="text-sm text-[#94A3B8]">
                  {testimonial.organization}
                </div>
              </div>
            </motion.div>
          ))}
        </div>

        {/* Stats Banner */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.5, duration: 0.6 }}
          className="mt-16 bg-gradient-to-r from-[#0EA5E9]/10 via-[#22C55E]/10 to-[#0EA5E9]/10 rounded-2xl p-8 border border-[#E2E8F0]"
        >
          <div className="grid sm:grid-cols-3 gap-8 text-center">
            <div>
              <div className="text-4xl font-bold text-[#0F172A] mb-2">
                250+
              </div>
              <div className="text-sm text-[#475569]">
                Laboratories using ASPIRA
              </div>
            </div>
            <div className="sm:border-x border-[#E2E8F0]">
              <div className="text-4xl font-bold text-[#0F172A] mb-2">
                50M+
              </div>
              <div className="text-sm text-[#475569]">
                Samples processed annually
              </div>
            </div>
            <div>
              <div className="text-4xl font-bold text-[#0F172A] mb-2">
                99.97%
              </div>
              <div className="text-sm text-[#475569]">
                Customer satisfaction rate
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
