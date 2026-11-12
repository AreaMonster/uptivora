import type { ReactNode } from "react";

export function SettingsSection({
  id,
  title,
  description,
  children,
}: {
  id?: string;
  title: string;
  description?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className="grid scroll-mt-20 gap-6 border-b border-line py-8 first:pt-0 last:border-0 lg:grid-cols-[260px_1fr]"
    >
      <div>
        <h2 className="font-semibold">{title}</h2>
        {description && <p className="mt-1 text-sm text-fg-muted">{description}</p>}
      </div>
      <div className="card min-w-0 p-6">{children}</div>
    </section>
  );
}
