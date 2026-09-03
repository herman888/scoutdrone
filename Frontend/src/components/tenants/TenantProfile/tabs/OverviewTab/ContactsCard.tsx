import React from 'react';

interface EmergencyContact {
  id?: string;
  name: string;
  relationship: string;
  phone: string;
  email?: string;
  is_primary?: boolean;
}

interface ContactsCardProps {
  tenantName: string;
  tenantEmail?: string;
  tenantPhone?: string;
  emergencyContacts: EmergencyContact[];
  onAddContact: () => void;
  onEditContact: (contact: EmergencyContact) => void;
  onDeleteContact: (index: number) => void;
}

const ContactsCard: React.FC<ContactsCardProps> = ({
  tenantName,
  tenantEmail,
  tenantPhone,
  emergencyContacts,
  onAddContact,
  onEditContact,
  onDeleteContact,
}) => {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4 flex flex-col">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
        <svg className="w-4 h-4 text-blue-600 dark:text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
        </svg>
        Contacts
      </h3>

      <div className="flex-1 overflow-auto space-y-3">
        {/* Tenant Contact */}
        <div className="space-y-1.5">
          <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Tenant</div>
          <div className="text-sm font-medium text-gray-900 dark:text-gray-100">{tenantName}</div>
          {(tenantEmail || tenantPhone) && (
            <div className="flex flex-col gap-0.5">
              {tenantEmail && (
                <a
                  href={`mailto:${tenantEmail}`}
                  className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 flex items-center gap-1"
                  title={tenantEmail}
                >
                  <svg className="w-3 h-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                  <span className="truncate">{tenantEmail}</span>
                </a>
              )}
              {tenantPhone && (
                <a
                  href={`tel:${tenantPhone}`}
                  className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 flex items-center gap-1"
                >
                  <svg className="w-3 h-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                  </svg>
                  <span>{tenantPhone}</span>
                </a>
              )}
            </div>
          )}
        </div>

        {/* Emergency Contacts */}
        <div className="pt-3 border-t border-gray-100 dark:border-gray-700">
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Emergency Contacts</div>
            <button
              onClick={onAddContact}
              className="text-xs font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 transition-colors"
            >
              + Add
            </button>
          </div>

          {emergencyContacts.length > 0 ? (
            <div className="space-y-2">
              {emergencyContacts.slice(0, 3).map((contact, index) => (
                <div key={contact.id || index} className="group">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{contact.name}</span>
                      {contact.is_primary && (
                        <span className="text-[10px] bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 px-1 py-0.5 rounded flex-shrink-0">
                          Primary
                        </span>
                      )}
                    </div>
                    <div className="opacity-0 group-hover:opacity-100 transition-opacity flex gap-1 flex-shrink-0">
                      <button
                        onClick={() => onEditContact(contact)}
                        className="text-[10px] text-gray-500 hover:text-blue-600 dark:hover:text-blue-400"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => onDeleteContact(index)}
                        className="text-[10px] text-gray-500 hover:text-red-600 dark:hover:text-red-400"
                      >
                        Del
                      </button>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 mt-0.5">
                    <span className="text-xs text-gray-500 dark:text-gray-400">{contact.relationship}</span>
                    <a href={`tel:${contact.phone}`} className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 flex items-center gap-1">
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                      </svg>
                      {contact.phone}
                    </a>
                  </div>
                </div>
              ))}
              {emergencyContacts.length > 3 && (
                <p className="text-xs text-gray-400 dark:text-gray-500">+{emergencyContacts.length - 3} more</p>
              )}
            </div>
          ) : (
            <p className="text-xs text-gray-400 dark:text-gray-500 italic">None added</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default ContactsCard;
