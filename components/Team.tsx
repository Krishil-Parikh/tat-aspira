import { motion } from 'motion/react';
import { Linkedin, Mail } from 'lucide-react';

export function Team() {
  const team = [
    {
      name: 'Dr. Alex Morgan',
      role: 'Chief Executive Officer',
      expertise: 'Biotech & Lab Systems',
    },
    {
      name: 'Dr. Sarah Chen',
      role: 'Chief Technology Officer',
      expertise: 'Distributed Systems',
    },
    {
      name: 'Michael Rodriguez',
      role: 'Head of Engineering',
      expertise: 'Real-Time Processing',
    },
    {
      name: 'Dr. Emily Watson',
      role: 'Chief Science Officer',
      expertise: 'Clinical Research',
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
          className="text-center mb-16"
        >
          <div className="inline-flex items-center space-x-2 px-4 py-2 bg-white rounded-full border border-[#E2E8F0] mb-6">
            <div className="w-2 h-2 bg-[#0EA5E9] rounded-full" />
            <span className="text-sm font-medium text-[#475569]">Our Team</span>
          </div>
          <h2 className="text-4xl sm:text-5xl font-bold text-[#0F172A] mb-4">
            Built by Experts
          </h2>
          <p className="text-lg text-[#475569] max-w-2xl mx-auto">
            A team of engineers and scientists dedicated to advancing laboratory technology
          </p>
        </motion.div>

        {/* Team Grid */}
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {team.map((member, index) => (
            <motion.div
              key={member.name}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: index * 0.1, duration: 0.6 }}
              whileHover={{ y: -8 }}
              className="bg-white rounded-2xl p-6 border border-[#E2E8F0] hover:border-[#CBD5E1] transition-all group"
            >
              {/* Avatar Placeholder */}
              <div className="w-20 h-20 bg-gradient-to-br from-[#0EA5E9]/20 to-[#22C55E]/20 rounded-2xl mb-4 flex items-center justify-center">
                <span className="text-2xl font-bold text-[#0EA5E9]">
                  {member.name.split(' ').map(n => n[0]).join('')}
                </span>
              </div>

              {/* Info */}
              <div className="space-y-2 mb-4">
                <h3 className="font-bold text-[#0F172A]">{member.name}</h3>
                <div className="text-sm text-[#475569]">{member.role}</div>
                <div className="text-xs text-[#64748B] pt-2 border-t border-[#E2E8F0]">
                  {member.expertise}
                </div>
              </div>

              {/* Social Links */}
              <div className="flex space-x-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <button className="w-8 h-8 bg-[#F1F5F9] hover:bg-[#0EA5E9] hover:text-white rounded-lg flex items-center justify-center transition-colors">
                  <Linkedin size={16} />
                </button>
                <button className="w-8 h-8 bg-[#F1F5F9] hover:bg-[#0EA5E9] hover:text-white rounded-lg flex items-center justify-center transition-colors">
                  <Mail size={16} />
                </button>
              </div>
            </motion.div>
          ))}
        </div>

        {/* Join CTA */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.4, duration: 0.6 }}
          className="mt-16 text-center"
        >
          <div className="bg-white rounded-2xl p-12 border border-[#E2E8F0]">
            <h3 className="text-2xl font-bold text-[#0F172A] mb-4">
              Join Our Team
            </h3>
            <p className="text-[#475569] mb-8 max-w-2xl mx-auto">
              We're always looking for talented engineers and scientists to help us build the future of laboratory systems
            </p>
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              className="px-8 py-3 bg-[#0EA5E9] text-white font-medium rounded-xl hover:bg-[#0284C7] transition-colors shadow-lg shadow-[#0EA5E9]/20"
            >
              View Open Positions
            </motion.button>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
