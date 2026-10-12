import { motion } from 'motion/react';
import { ArrowRight, Github, Linkedin, Twitter } from 'lucide-react';

export function FooterCTA() {
  const footerLinks = {
    Product: ['Features', 'Pricing', 'Documentation', 'API Reference'],
    Company: ['About', 'Team', 'Careers', 'Contact'],
    Resources: ['Blog', 'Case Studies', 'Support', 'Status'],
    Legal: ['Privacy', 'Terms', 'Security', 'Compliance'],
  };

  return (
    <footer className="bg-[#0F172A] text-white">
      {/* Final CTA Section */}
      <div className="border-b border-white/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="text-center max-w-4xl mx-auto"
          >
            <h2 className="text-4xl sm:text-5xl lg:text-6xl font-bold mb-6">
              Ready to Transform Your Lab?
            </h2>
            <p className="text-lg sm:text-xl text-white/70 mb-10 max-w-2xl mx-auto">
              Join 250+ laboratories worldwide using ASPIRA for high-throughput, reliable processing
            </p>
            <div className="flex flex-wrap justify-center gap-4">
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="px-8 py-4 bg-[#0EA5E9] text-white font-medium rounded-xl hover:bg-[#0284C7] transition-colors shadow-2xl shadow-[#0EA5E9]/30 flex items-center space-x-2"
              >
                <span>Start Scanning</span>
                <ArrowRight size={18} />
              </motion.button>
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="px-8 py-4 bg-white/10 backdrop-blur-sm text-white font-medium rounded-xl hover:bg-white/20 transition-colors border border-white/20"
              >
                Schedule Demo
              </motion.button>
            </div>

            {/* Trust Badges */}
            <div className="mt-12 pt-12 border-t border-white/10">
              <div className="grid sm:grid-cols-3 gap-8 text-center">
                <div>
                  <div className="text-3xl font-bold mb-2">ISO 9001</div>
                  <div className="text-sm text-white/60">Quality Certified</div>
                </div>
                <div>
                  <div className="text-3xl font-bold mb-2">SOC 2</div>
                  <div className="text-sm text-white/60">Security Compliant</div>
                </div>
                <div>
                  <div className="text-3xl font-bold mb-2">HIPAA</div>
                  <div className="text-sm text-white/60">Data Protected</div>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </div>

      {/* Footer Links */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="grid sm:grid-cols-2 lg:grid-cols-6 gap-12">
          {/* Brand Column */}
          <div className="lg:col-span-2">
            <div className="flex items-center space-x-2 mb-4">
              <div className="w-8 h-8 bg-[#0EA5E9] rounded-lg flex items-center justify-center">
                <span className="text-white text-sm font-bold">AS</span>
              </div>
              <span className="text-white font-bold text-lg">ASPIRA</span>
            </div>
            <p className="text-white/60 text-sm leading-relaxed mb-6">
              Production-grade laboratory infrastructure for high-throughput, low-latency processing.
            </p>
            <div className="flex space-x-3">
              {[Twitter, Linkedin, Github].map((Icon, i) => (
                <motion.a
                  key={i}
                  href="#"
                  whileHover={{ scale: 1.1, y: -2 }}
                  className="w-10 h-10 bg-white/10 hover:bg-[#0EA5E9] rounded-lg flex items-center justify-center transition-colors"
                >
                  <Icon size={18} />
                </motion.a>
              ))}
            </div>
          </div>

          {/* Link Columns */}
          {Object.entries(footerLinks).map(([category, links]) => (
            <div key={category}>
              <h3 className="font-semibold mb-4">{category}</h3>
              <ul className="space-y-3">
                {links.map((link) => (
                  <li key={link}>
                    <a
                      href="#"
                      className="text-sm text-white/60 hover:text-white transition-colors"
                    >
                      {link}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      {/* Bottom Bar */}
      <div className="border-t border-white/10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex flex-col sm:flex-row justify-between items-center space-y-4 sm:space-y-0">
            <div className="text-sm text-white/60">
              © {new Date().getFullYear()} ASPIRA. All rights reserved.
            </div>
            <div className="flex items-center space-x-1 text-sm text-white/60">
              <span>Built for reliability.</span>
              <span className="text-[#22C55E]">●</span>
              <span>Engineered for speed.</span>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
