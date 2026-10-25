from babelko.validation import repeated_top_text


def test_doubled_rendered_header_is_detected_without_flagging_body():
    header='Dip et al: NeuroSleepNet: 공간 및 다중 규모의 시간적 맥락 학습을 통한 자동 수면 단계 분석용 설명 가능한 다중 헤드 어텐션 기반 프레임워크'
    spans=[{'text':header+header,'bbox':(40,28,550,39)}]
    assert repeated_top_text(spans,792)
    assert not repeated_top_text([{'text':header,'bbox':(40,28,400,39)}],792)
    assert not repeated_top_text([{'text':header+header,'bbox':(40,130,550,141)}],792)
