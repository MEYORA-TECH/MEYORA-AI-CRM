import type { components } from "./api";

type S = components["schemas"];

export type Me = S["MeOut"];
export type TokenResponse = S["TokenOut"];
export type Role = S["Role"];
export type Perm = S["Perm"];

export type Company = S["CompanyOut"];
export type CompanyInput = S["CompanyCreate"];
export type Contact = S["ContactOut"];
export type ContactInput = S["ContactCreate"];
export type Lead = S["LeadOut"];
export type LeadInput = S["LeadCreate"];
export type LeadConvertInput = S["LeadConvertIn"];
export type LeadConvertResult = S["LeadConvertOut"];
export type Deal = S["DealOut"];
export type DealInput = S["DealCreate"];
export type Board = S["BoardOut"];
export type BoardColumn = S["BoardColumn"];
export type Activity = S["ActivityOut"];
export type ActivityInput = S["ActivityCreate"];
export type Task = S["TaskOut"];
export type TaskInput = S["TaskCreate"];
export type Note = S["NoteOut"];
export type TimelineItem = S["TimelineItem"];
export type Pipeline = S["PipelineOut"];
export type Stage = S["StageOut"];
export type Dashboard = S["DashboardOut"];
export type Member = S["MemberOut"];
export type Invitation = S["InvitationOut"];
export type InvitationCreated = S["InvitationCreated"];
export type AuditLog = S["AuditLogOut"];
export type Organization = S["OrganizationDetailOut"];

export type CompanyStatus = S["CompanyStatus"];
export type LeadStatus = S["LeadStatus"];
export type DealStatus = S["DealStatus"];
export type TaskStatus = S["TaskStatus"];
export type TaskPriority = S["TaskPriority"];
export type ActivityType = S["ActivityType"];

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
