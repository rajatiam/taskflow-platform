export type Value = string | number | boolean | null | string[];
export interface RecordItem {
  id: number;
  [key: string]: unknown;
}
export interface ProjectConfig {
  name: string;
  skills: string;
  entity: string;
  kind: string;
  port: number;
  fields: string[];
  example: Record<string, Value>;
  description: string;
  accent: string;
}
export interface Field {
  key: string;
  label: string;
  type: 'text' | 'number' | 'datetime-local' | 'select' | 'textarea';
  options: string[];
  step: string;
}
