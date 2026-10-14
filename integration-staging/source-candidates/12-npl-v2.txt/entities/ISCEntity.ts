import { Entity, PrimaryColumn, Column } from 'typeorm';

@Entity('isc_versions')
export class ISCEntity {
  @PrimaryColumn() userId: string;
  @Column() version: number;
  @Column('jsonb') constraints: Record<string, any>; // stores AbsoluteConstraint objects (domains as array)
  @Column() checksum: string;
  @Column() createdAt: Date;
  @Column() updatedAt: Date;
  @Column() isActive: boolean;
}
