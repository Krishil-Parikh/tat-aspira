import { motion } from 'motion/react';
import { Mail, MapPin, Phone, Send } from 'lucide-react';
import { useState } from 'react';

export function Contact() {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    organization: '',
    message: '',
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Handle form submission
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
  };

  const contactInfo = [
    {
      icon: Mail,
      label: 'Email',
      value: 'contact@aspira.com',
      href: 'mailto:contact@aspira.com',
    },
    {
      icon: Phone,
      label: 'Phone',
      value: '+1 (555) 123-4567',
      href: 'tel:+15551234567',
    },
    {
      icon: MapPin,
      label: 'Address',
      value: 'San Francisco, CA 94103',
      href: '#',
    },
  ];

  return (
    <section id="contact" className="py-24 px-4 sm:px-6 lg:px-8 bg-white">
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
            <Mail size={16} className="text-[#0EA5E9]" />
            <span className="text-sm font-medium text-[#475569]">
              Get in Touch
            </span>
          </div>
          <h2 className="text-4xl sm:text-5xl font-bold text-[#0F172A] mb-4">
            Contact Us
          </h2>
          <p className="text-lg text-[#475569] max-w-2xl mx-auto">
            Ready to transform your laboratory operations? Reach out to our team
          </p>
        </motion.div>

        <div className="grid lg:grid-cols-3 gap-12">
          {/* Contact Info */}
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="space-y-8"
          >
            <div>
              <h3 className="text-2xl font-bold text-[#0F172A] mb-6">
                Contact Information
              </h3>
              <p className="text-[#475569] leading-relaxed mb-8">
                Have questions about ASPIRA? Our team is here to help you get started.
              </p>
            </div>

            <div className="space-y-6">
              {contactInfo.map((info, index) => (
                <motion.a
                  key={info.label}
                  href={info.href}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: index * 0.1 }}
                  whileHover={{ x: 4 }}
                  className="flex items-start space-x-4 p-4 bg-[#F8FAFC] rounded-xl border border-[#E2E8F0] hover:border-[#CBD5E1] transition-all group"
                >
                  <div className="w-10 h-10 bg-[#0EA5E9]/10 rounded-lg flex items-center justify-center flex-shrink-0 group-hover:bg-[#0EA5E9]/20 transition-colors">
                    <info.icon size={20} className="text-[#0EA5E9]" />
                  </div>
                  <div>
                    <div className="text-sm text-[#64748B] mb-1">
                      {info.label}
                    </div>
                    <div className="font-medium text-[#0F172A]">
                      {info.value}
                    </div>
                  </div>
                </motion.a>
              ))}
            </div>

            {/* Office Hours */}
            <div className="bg-gradient-to-br from-[#0EA5E9]/10 to-[#22C55E]/10 rounded-xl p-6 border border-[#E2E8F0]">
              <h4 className="font-semibold text-[#0F172A] mb-4">
                Office Hours
              </h4>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-[#475569]">Monday - Friday</span>
                  <span className="font-medium text-[#0F172A]">9am - 6pm PST</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#475569]">Saturday - Sunday</span>
                  <span className="font-medium text-[#0F172A]">Closed</span>
                </div>
              </div>
            </div>
          </motion.div>

          {/* Contact Form */}
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="lg:col-span-2"
          >
            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="grid sm:grid-cols-2 gap-6">
                <div>
                  <label
                    htmlFor="name"
                    className="block text-sm font-medium text-[#0F172A] mb-2"
                  >
                    Full Name
                  </label>
                  <input
                    type="text"
                    id="name"
                    name="name"
                    value={formData.name}
                    onChange={handleChange}
                    required
                    className="w-full px-4 py-3 bg-[#F8FAFC] border border-[#E2E8F0] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#0EA5E9] focus:border-transparent transition-all text-[#0F172A]"
                    placeholder="John Doe"
                  />
                </div>

                <div>
                  <label
                    htmlFor="email"
                    className="block text-sm font-medium text-[#0F172A] mb-2"
                  >
                    Email Address
                  </label>
                  <input
                    type="email"
                    id="email"
                    name="email"
                    value={formData.email}
                    onChange={handleChange}
                    required
                    className="w-full px-4 py-3 bg-[#F8FAFC] border border-[#E2E8F0] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#0EA5E9] focus:border-transparent transition-all text-[#0F172A]"
                    placeholder="john@example.com"
                  />
                </div>
              </div>

              <div>
                <label
                  htmlFor="organization"
                  className="block text-sm font-medium text-[#0F172A] mb-2"
                >
                  Organization
                </label>
                <input
                  type="text"
                  id="organization"
                  name="organization"
                  value={formData.organization}
                  onChange={handleChange}
                  required
                  className="w-full px-4 py-3 bg-[#F8FAFC] border border-[#E2E8F0] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#0EA5E9] focus:border-transparent transition-all text-[#0F172A]"
                  placeholder="Your laboratory or organization"
                />
              </div>

              <div>
                <label
                  htmlFor="message"
                  className="block text-sm font-medium text-[#0F172A] mb-2"
                >
                  Message
                </label>
                <textarea
                  id="message"
                  name="message"
                  value={formData.message}
                  onChange={handleChange}
                  required
                  rows={6}
                  className="w-full px-4 py-3 bg-[#F8FAFC] border border-[#E2E8F0] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#0EA5E9] focus:border-transparent transition-all resize-none text-[#0F172A]"
                  placeholder="Tell us about your lab's needs..."
                />
              </div>

              <motion.button
                type="submit"
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className="w-full px-8 py-4 bg-[#0EA5E9] text-white font-medium rounded-xl hover:bg-[#0284C7] transition-colors shadow-lg shadow-[#0EA5E9]/20 flex items-center justify-center space-x-2"
              >
                <span>Send Message</span>
                <Send size={18} />
              </motion.button>

              <p className="text-sm text-[#64748B] text-center">
                We typically respond within 24 hours during business days
              </p>
            </form>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
