import { ISCEngine } from '../../engine/ISCEngine';
test('ISC hard veto denies', async () => {
  const engine = new ISCEngine(mockRepo, mockAudit, []);
  const result = await engine.isAllowed('u1', { COLOR: 'red' }, 'req');
  expect(result.allowed).toBe(false);
});
