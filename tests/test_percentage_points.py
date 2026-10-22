import pytest
from babelko.hybrid import errors


@pytest.mark.parametrize('source,target',[
 ('The rate fell from 8% to 6%, a decrease of 2 percentage points.','비율은 8%에서 6%로 하락했다. 2%포인트 감소이다.'),
 ('The estimate rose by 0.5 percentage points.','추정치는 0.5%p 상승했다.'),
 ('The estimate rose by two percentage points.','추정치는 2 퍼센트포인트 상승했다.'),
 ('A decrease of -1.25 percent points was recorded.','-1.25%포인트의 감소가 기록되었다.'),
 ('The rate changed by 2%.','비율이 2% 변했다.'),
 ('The rate changed by half a percentage point.','비율이 0.5%포인트 변했다.'),
 ('The rate changed by 1/2 percentage point.','비율이 1/2%포인트 변했다.'),
 ('The rate changed by 2e-3 percentage points.','비율이 2e-3%포인트 변했다.'),
])
def test_equivalent_percentage_point_values_and_other_units_remain_valid(source,target):
    assert not errors(source,target)


@pytest.mark.parametrize('source,target',[
 ('The rate fell from 8% to 6%, a decrease of 2 percentage points.','비율은 8%에서 6%로 하락했다. 2% 감소이다.'),
 ('The estimate rose by 0.5%.','추정치는 0.5%p 상승했다.'),
 ('The effect changed by 1 percentage point and the rate by 2%.','효과가 1% 변했고 비율이 2%포인트 변했다.'),
 ('The rate changed by -0.5 percentage points.','비율이 0.5%포인트 변했다.'),
 ('The rate changed by 2.0 percentage points.','비율이 2%포인트 변했다.'),
])
def test_percent_confusion_value_swaps_and_signs_are_rejected(source,target):
    assert errors(source,target)
