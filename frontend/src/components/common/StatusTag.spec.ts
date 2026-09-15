import { mount } from '@vue/test-utils'

import StatusTag from '@/components/common/StatusTag.vue'

describe('StatusTag', () => {
  it('renders a human-readable clarification signal', () => {
    const wrapper = mount(StatusTag, {
      props: { status: 'CLARIFICATION_REQUIRED', kind: 'expected' },
      global: {
        stubs: {
          'a-tag': { template: '<span class="tag"><slot /></span>' },
        },
      },
    })

    expect(wrapper.text()).toContain('需要澄清')
  })
})
